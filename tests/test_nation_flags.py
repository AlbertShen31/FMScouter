"""Nation label → ISO / Flagpedia / emoji helpers."""
from __future__ import annotations

import services.nation_flags as nf


def test_nation_iso2_labels_codes_and_blanks():
    assert nf.nation_iso2("Romania") == "RO"
    assert nf.nation_iso2("ROU") == "RO"
    assert nf.nation_iso2("England") == "GB-ENG"
    assert nf.nation_iso2("ENG") == "GB-ENG"
    assert nf.nation_iso2("-") == ""
    assert nf.nation_iso2("Unknown") == ""
    assert nf.nation_iso2(None) == ""


def test_flag_icon_src_and_iter():
    assert nf.flag_icon_src("RO") == "/assets/flags/ro.png"
    assert nf.flag_icon_src("GB-ENG") == "/assets/flags/gb-eng.png"
    assert nf.flag_icon_src("") == ""
    flags = nf.iter_nation_flags("Romania", "England")
    assert [code for code, _src, _alt in flags] == ["RO", "GB-ENG"]
    # Duplicates collapse.
    assert len(nf.iter_nation_flags("Romania", "ROU")) == 1
    assert nf.iter_nation_flags(None, "-") == []


def test_martinique_and_split_dual_nationality():
    assert nf.nation_iso2("Martinique") == "MQ"
    assert nf.nation_iso2("MTQ") == "MQ"
    assert nf.nation_iso2("MQ") == "MQ"
    assert [code for code, _src, _alt in nf.iter_nation_flags("France", "Martinique")] == [
        "FR",
        "MQ",
    ]
    # Combined Nat / 2nd-Nat strings from FM / save export.
    assert [code for code, _src, _alt in nf.iter_nation_flags("France/Martinique")] == [
        "FR",
        "MQ",
    ]
    assert [code for code, _src, _alt in nf.iter_nation_flags("FRA/MTQ")] == ["FR", "MQ"]
    html = nf.nation_flag_html("France", "Martinique")
    assert 'src="/assets/flags/fr.png"' in html
    assert 'src="/assets/flags/mq.png"' in html


def test_nation_flag_html_and_emoji():
    html = nf.nation_flag_html("Romania", "England")
    assert 'class="nation-flags"' in html
    assert 'src="/assets/flags/ro.png"' in html
    assert 'src="/assets/flags/gb-eng.png"' in html
    assert nf.nation_flag_html("-") == ""

    emoji = nf.nation_flag_emoji("Romania")
    assert emoji  # regional indicators
    eng = nf.nation_flag_emoji("England")
    assert eng.startswith("🏴")
    assert nf.nation_flag_emoji("Kosovo")  # XK private-use pair
    both = nf.nation_flag_emojis("Romania", "England")
    assert both.startswith(emoji)
    assert eng in both
    assert nf.nation_flag_emojis(None, None) == ""
    dual = nf.nation_flag_emojis("France/Martinique")
    assert nf.nation_flag_emoji("France") in dual
    assert nf.nation_flag_emoji("Martinique") in dual


def test_strip_nation_flags_removes_markup_and_emoji():
    html = nf.nation_flag_html("Romania") + "Ada"
    assert nf.strip_nation_flags(html) == "Ada"
    emoji = nf.nation_flag_emoji("France") + "\xa0Player"
    assert nf.strip_nation_flags(emoji) == "Player"
    assert nf.strip_nation_flags("Plain Name") == "Plain Name"
