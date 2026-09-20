import sys
from pathlib import Path
sys.path.insert(0, str(Path("backend")))
from backend.app.ingestion import ingestion_service
try:
    print(ingestion_service.ingest(days=1))
except Exception as e:
    import traceback
    traceback.print_exc()
