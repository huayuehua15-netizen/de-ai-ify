"""分句/语言判定单测：偏移不变量是高亮正确性的根基。"""

from deaiify.engine.segment import count_words, detect_lang, paragraphs_of, split_sentences


def test_split_keeps_offsets_invariant() -> None:
    text = "第一句。第二句！第三句？尾句。"
    sents = split_sentences(text)
    assert len(sents) == 4
    for s in sents:
        assert text[s.start : s.end] == s.text


def test_split_merges_closing_quotes() -> None:
    text = "他说：“走吧。”然后离开了。"
    sents = split_sentences(text)
    for s in sents:
        assert text[s.start : s.end] == s.text
    assert sents[0].text.endswith("。”")


def test_split_decimal_not_broken() -> None:
    text = "增长率是 3.14 倍。就这么简单。"
    sents = split_sentences(text)
    assert len(sents) == 2
    assert "3.14" in sents[0].text


def test_split_english_period() -> None:
    text = "First sentence. Second one! Third?"
    sents = split_sentences(text)
    assert len(sents) == 3
    for s in sents:
        assert text[s.start : s.end] == s.text


def test_split_newline_and_whitespace() -> None:
    text = "   \n  开头一句。  \n\n  结尾一句。  "
    sents = split_sentences(text)
    assert len(sents) == 2
    assert sents[0].text == "开头一句。"


def test_detect_lang_threshold() -> None:
    assert detect_lang("这是一段中文，含有少量 English。") == "zh"
    assert detect_lang("This is a pure English paragraph with 中文 two words only.") == "en"
    assert detect_lang("") == "zh"


def test_count_words_approx() -> None:
    assert count_words("hello world 42", "en") == 3
    zh = count_words("今天天气不错出去玩", "zh")
    assert 5 <= zh <= 10  # 10 字 ≈ 6 词
    assert count_words("", "zh") == 0


def test_paragraphs_skips_short_lines() -> None:
    text = "这一行足够长可以成为一段。\n短\n又一行长度足够的内容在这里。"
    spans = paragraphs_of(text)
    assert len(spans) == 2
