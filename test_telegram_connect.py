
import subprocess, os, json
with open('/tmp/tg_token.txt') as f:
    TOKEN = f.read().strip()
print('Token found:', bool(TOKEN))
if TOKEN:
    print('Token length:', len(TOKEN))
    result = subprocess.run(
        ['/mnt/c/Windows/System32/curl.exe', '-v', '--connect-timeout', '10',
         'https://api.telegram.org/bot' + TOKEN + '/getMe'],
        capture_output=True, text=True, timeout=15
    )
    print('STDOUT:', result.stdout[:300])
    print('STDERR:', result.stderr[:500])
    print('RC:', result.returncode)
