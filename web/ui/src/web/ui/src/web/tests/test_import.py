def test_import_app_module():
    import importlib
    mod = importlib.import_module("app.main")
    assert hasattr(mod, "app")
  
