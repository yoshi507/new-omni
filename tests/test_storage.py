from omnibot import storage


def test_read_does_not_create_file():
    path = storage._guild_path(111)
    data = storage.load_guild(111)
    assert isinstance(data, dict) and data
    assert not path.exists()


def test_roundtrip():
    storage.update_guild(222, lambda d: d.__setitem__("custom", {"a": 1}))
    assert storage.load_guild(222)["custom"] == {"a": 1}


def test_corrupt_file_is_quarantined_not_overwritten():
    path = storage._guild_path(333)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    data = storage.load_guild(333)
    assert isinstance(data, dict)
    assert not path.exists()
    backups = list(path.parent.glob("333.corrupt-*.json"))
    assert backups and backups[0].read_text() == "{ not json"
