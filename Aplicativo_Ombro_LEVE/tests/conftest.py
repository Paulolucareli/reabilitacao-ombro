import pytest
from streamlit.components.v2.component_manager import BidiComponentManager


@pytest.fixture(autouse=True)
def builtin_components_only(monkeypatch):
    # O app usa somente componentes embutidos; não depende de plugins instalados
    # no computador que executa a suíte.
    monkeypatch.setattr(BidiComponentManager, 'discover_and_register_components', lambda *args, **kwargs: None)
