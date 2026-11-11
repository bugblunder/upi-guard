"""Create local Docker secrets without printing them or overwriting existing config."""
import os
import secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1]
fd=os.open(root/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:
    f.write('APP_ENV=development\nSECRET_KEY='+secrets.token_hex(32)+'\nPOSTGRES_PASSWORD='+secrets.token_hex(24)+'\nTRUSTED_HOSTS=localhost,127.0.0.1\n')
print('Created .env with random local Docker secrets. Keep this file private.')
