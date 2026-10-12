package main

import (
	"bufio"
	"io"
	"net"
	"testing"
	"time"
)

func TestMCPProxyZeroWriteFixture(t *testing.T) {
	listener, path := mcpProxySocket(t)
	client, err := net.DialUnix("unix", nil, &net.UnixAddr{Name: path, Net: "unix"})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	backend := acceptMCPProxy(t, listener)
	if err := backend.CloseRead(); err != nil {
		t.Fatal(err)
	}
	if n, err := client.Write([]byte("unwritten\n")); n != 0 || err == nil {
		t.Fatalf("half-close fixture Write = %d, %v; want zero bytes and an error", n, err)
	}
	if _, err := backend.Write([]byte("still-open\n")); err != nil {
		t.Fatal(err)
	}
	if err := client.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	line, err := bufio.NewReader(client).ReadString('\n')
	if err != nil || line != "still-open\n" {
		t.Fatalf("half-close fixture output %q, %v; want an open write half", line, err)
	}
}

func TestMCPProxyZeroWriteRecovery(t *testing.T) {
	for _, partial := range []bool{false, true} {
		name := "whole-unwritten-request"
		if partial {
			name = "continuation-after-written-prefix"
		}
		t.Run(name, func(t *testing.T) {
			listener, path := mcpProxySocket(t)
			f := newMCPProxyFixture(t, path)
			first := acceptMCPProxy(t, listener)
			exchangeMCPProxy(t, f, first, "healthy-before-half-close")

			if partial {
				prefix := `{"jsonrpc":"2.0","method":"part`
				if _, err := io.WriteString(f.input, prefix); err != nil {
					t.Fatal(err)
				}
				if err := first.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
					t.Fatal(err)
				}
				got := make([]byte, len(prefix))
				if _, err := io.ReadFull(first, got); err != nil || string(got) != prefix {
					t.Fatalf("backend prefix %q, %v; want %q", got, err, prefix)
				}
			}

			// Keep the backend's write half open: the proxy output reader cannot
			// observe EOF before the next stdin chunk reaches its socket Write.
			if err := first.CloseRead(); err != nil {
				t.Fatal(err)
			}
			pending := `{"jsonrpc":"2.0","method":"pending","id":1}` + "\n"
			if partial {
				pending = `ial","id":1}` + "\n"
			}
			if _, err := io.WriteString(f.input, pending); err != nil {
				t.Fatal(err)
			}

			second := acceptMCPProxy(t, listener)
			want := pending
			if partial {
				// A zero-byte write of this chunk does not make it a whole
				// request: its prefix went to the previous socket generation.
				want = `{"jsonrpc":"2.0","method":"next","id":2}` + "\n"
				if _, err := io.WriteString(f.input, want); err != nil {
					t.Fatal(err)
				}
			}
			if err := second.SetReadDeadline(time.Now().Add(2 * time.Second)); err != nil {
				t.Fatal(err)
			}
			line, err := bufio.NewReader(second).ReadString('\n')
			if err != nil || line != want {
				t.Fatalf("reconnected backend got %q, %v; want %q", line, err, want)
			}
			exchangeMCPProxy(t, f, second, "healthy-after-half-close")
			assertMCPProxyEOFExit(t, f)
		})
	}
}
