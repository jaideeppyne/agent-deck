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
	for _, name := range []string{"whole-unwritten-request", "continuation-after-written-prefix",
		"continuation-spans-new-input", "backend-close-with-incomplete-request"} {
		t.Run(name, func(t *testing.T) {
			partial := name != "whole-unwritten-request"
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
			var closeErr error
			if name == "backend-close-with-incomplete-request" {
				closeErr = first.Close()
			} else {
				closeErr = first.CloseRead()
			}
			if closeErr != nil {
				t.Fatal(closeErr)
			}
			pending := `{"jsonrpc":"2.0","method":"pending","id":1}` + "\n"
			if partial {
				pending = `ial","id":1}` + "\n"
			}
			if name == "continuation-spans-new-input" {
				pending = "i"
			}
			if name != "backend-close-with-incomplete-request" {
				if _, err := io.WriteString(f.input, pending); err != nil {
					t.Fatal(err)
				}
			}

			second := acceptMCPProxy(t, listener)
			want := pending
			if partial {
				// A zero-byte write of this chunk does not make it a whole
				// request: its prefix went to the previous socket generation.
				want = `{"jsonrpc":"2.0","method":"next","id":2}` + "\n"
				remaining := want
				if name == "continuation-spans-new-input" {
					remaining = `al","id":1}` + "\n" + want
				} else if name == "backend-close-with-incomplete-request" {
					remaining = pending + want
				}
				if _, err := io.WriteString(f.input, remaining); err != nil {
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
