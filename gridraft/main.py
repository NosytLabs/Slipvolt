"""ASGI entry point. Persistent storage is mandatory outside local evaluation."""
import os
from pathlib import Path
from .app import Settings, create_app
path=os.getenv('DATABASE_PATH','data/gridraft.db')
Path(path).parent.mkdir(parents=True,exist_ok=True)
app=create_app(Settings.from_env(),path)
