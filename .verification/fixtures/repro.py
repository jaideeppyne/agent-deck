import hashlib
import json
import os
import pathlib
import subprocess
import sys


def main():
    binary = sys.argv[1]
    home = pathlib.Path('/work/home')
    project = home / 'project'
    shared = home / 'shared'
    config_root = home / '.agent-deck'
    for path in (home, project, shared, config_root):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    config = []
    for account in ('personal', 'work'):
        root = home / ('.claude-' + account)
        root.mkdir(mode=0o700)
        (root / 'projects').symlink_to(shared, target_is_directory=True)
        config.append('[profiles.' + account + '.claude]\nconfig_dir = ' + json.dumps(str(root)))
    (config_root / 'config.toml').write_text('\n'.join(config) + '\n')
    env = {
        'HOME': str(home), 'PATH': '/usr/local/bin:/usr/bin:/bin',
        'TERM': 'dumb', 'TMUX_TMPDIR': '/work/tmux',
        'AGENTDECK_PROFILE': 'shared-store-repro',
        'AGENTDECK_SKIP_UPDATE_CHECK': '1', 'AGENTDECK_TELEMETRY': '0',
    }

    def run(*args):
        result = subprocess.run([binary, *args], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        print('COMMAND:', ' '.join(args))
        print('EXIT:', result.returncode)
        print('STDOUT:', result.stdout)
        print('STDERR:', result.stderr)
        return result

    added = run('add', '-t', 'shared-store-repro', '-c', 'claude', '--no-parent',
                '--account', 'personal', '--json', str(project))
    if added.returncode:
        return 2
    deck_id = json.loads(added.stdout)['id']
    sid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    seeded = run('session', 'set', deck_id, 'claude-session-id', sid)
    if seeded.returncode:
        return 2
    slug = str(project).replace('/', '-').replace('.', '-')
    transcript = shared / slug / (sid + '.jsonl')
    transcript.parent.mkdir(mode=0o700)
    body = json.dumps({'sessionId': sid, 'type': 'user', 'timestamp': '2026-10-10T00:00:00Z', 'message': 'shared'}) + '\n'
    transcript.write_text(body)
    before = hashlib.sha256(transcript.read_bytes()).hexdigest()
    switched = run('session', 'switch-account', deck_id, 'work', '--no-restart', '--json')
    after = hashlib.sha256(transcript.read_bytes()).hexdigest()
    print('TRANSCRIPT_UNCHANGED:', before == after)
    if before != after:
        return 2
    if switched.returncode and 'unsafe exact Claude source path' in switched.stdout + switched.stderr and 'symlink' in switched.stdout + switched.stderr:
        print('ORACLE: shared-store refusal reproduced')
        return 1
    if switched.returncode == 0:
        response = json.loads(switched.stdout)
        if response.get('success') and response.get('new_account') == 'work':
            print('ORACLE: shared-store account switch succeeded without transcript changes')
            return 0
    return 2


try:
    sys.exit(main())
except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
    print('HARNESS_ERROR:', error)
    sys.exit(2)
