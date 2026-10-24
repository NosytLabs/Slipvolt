"""ASGI entry point. Persistent storage is mandatory outside local evaluation."""
import os
from pathlib import Path
from .app import Settings, create_app
from .token_audit_api import install_token_audit_routes
path=os.getenv('DATABASE_PATH','data/gridraft.db')
Path(path).parent.mkdir(parents=True,exist_ok=True)
settings=Settings.from_env()
app=create_app(settings,path)
install_token_audit_routes(app,settings)
