from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Plugin:
    name: str
    description: str
    schemas: list[dict] = field(default_factory=list)
    implementations: dict[str, Callable] = field(default_factory=dict)
    prompt_fragment: str = ""


class PluginRegistry:
    def __init__(self):
        self._plugins: list[Plugin] = []

    def register(self, plugin: Plugin):
        names = {s["name"] for s in plugin.schemas}
        for existing in self._plugins:
            clash = names & {s["name"] for s in existing.schemas}
            if clash:
                raise ValueError(
                    f"Plugin '{plugin.name}' declares tools already provided by "
                    f"'{existing.name}': {sorted(clash)}"
                )
        self._plugins.append(plugin)

    def schemas(self) -> list[dict]:
        out = []
        for p in self._plugins:
            out.extend(p.schemas)
        return out

    def implementations(self) -> dict[str, Callable]:
        out = {}
        for p in self._plugins:
            out.update(p.implementations)
        return out

    def prompt_fragments(self) -> str:
        parts = [p.prompt_fragment for p in self._plugins if p.prompt_fragment]
        return "\n\n".join(parts)

    def loaded(self) -> list[str]:
        return [p.name for p in self._plugins]