import json

from omnibot.web import sessions


def test_tokens_and_sids_not_stored_in_plaintext():
    sid = sessions.create({"id": "1", "username": "u"}, "SECRET-ACCESS-TOKEN")
    raw = sessions._STORE.read_text()
    assert "SECRET-ACCESS-TOKEN" not in raw
    assert sid not in raw
    assert sessions.get(sid)["access_token"] == "SECRET-ACCESS-TOKEN"
    stored = json.loads(raw)
    assert all("access_token_enc" in v and "access_token" not in v for v in stored.values())


def test_destroy():
    sid = sessions.create({"id": "2"}, "t")
    sessions.destroy(sid)
    assert sessions.get(sid) is None


def test_oauth_state_single_use_and_bound_to_cookie():
    st = sessions.new_oauth_state()
    assert not sessions.consume_oauth_state(st, "different")
    st2 = sessions.new_oauth_state()
    assert sessions.consume_oauth_state(st2, st2)
    assert not sessions.consume_oauth_state(st2, st2)  # replay
    assert not sessions.consume_oauth_state(None, None)


def test_stale_guild_cache_is_capped():
    sess = {"guilds": [{"id": "1"}], "guilds_fetched_at": 0}
    assert sessions.get_cached_guilds(sess, allow_stale=True) is None
