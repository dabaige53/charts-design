"""Select a fixed project service per request; never switch a shared current project."""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock
from typing import Protocol

from .model import require
from .service import Service


class ProjectResolver(Protocol):
    def resolve(self, arguments: dict) -> tuple[Service, dict]: ...


class ProjectServices:
    def __init__(self, default: Service):
        self.default = default
        self.root = Path(getattr(default.store, 'runtime_root', default.store.root)).resolve()
        self._services: dict[Path, Service] = {}
        self._lock = Lock()
        if default.project_root:
            self._services[Path(default.project_root).resolve()] = default

    def resolve(self, arguments: dict) -> tuple[Service, dict]:
        request = dict(arguments)
        if 'projectRoot' not in request:
            return self.default, request
        value = request.pop('projectRoot')
        require(isinstance(value, str) and bool(value), 'projectRoot must be an absolute project directory', 'INVALID_PROJECT')
        path = Path(value).expanduser()
        require(path.is_absolute(), 'projectRoot must be an absolute project directory', 'INVALID_PROJECT')
        project = path.resolve()
        require(not project.exists() or project.is_dir(), 'projectRoot must be a directory', 'INVALID_PROJECT')
        with self._lock:
            service = self._services.get(project)
            if service is None:
                key = hashlib.sha256(str(project).encode()).hexdigest()[:24]
                service = Service(self.root / 'projects' / key, project_root=project)
                # Source aliases remain operator configured, not supplied by tool callers.
                service.queries = self.default.queries
                self._services[project] = service
        return service, request


def project_result(result: dict, service: Service) -> dict:
    project = str(Path(service.project_root).resolve()) if service.project_root else None
    return {**result, 'projectRoot': project}


def project_schema(schema: dict) -> dict:
    return {**schema, 'properties': {**schema.get('properties', {}), 'projectRoot': {
        'type': 'string', 'description': 'Absolute project asset directory. Pass it on every project request; omission uses only the startup default, never the last project.'}}}
