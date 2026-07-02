from tutorial_builder.tools.html_tools import parse_blocks, session_title


def test_parse_prose_splits_on_headings():
    html = "<html><body><h1>Session</h1><h2>A</h2><p>alpha text</p>" \
           "<h2>B</h2><p>beta text</p></body></html>"
    blocks = parse_blocks(html)
    titles = [b.title for b in blocks]
    assert "A" in titles and "B" in titles
    assert all(b.content_html for b in blocks)


def test_headingless_is_one_block():
    blocks = parse_blocks("<html><body><p>just text, no headings</p></body></html>")
    assert len(blocks) == 1
    assert blocks[0].word_count >= 3


def test_images_inventoried_with_occurrences():
    html = ("<h2>Models</h2><img src='w.png' alt='waterfall'>"
            "<h2>More</h2><img src='w.png' alt='waterfall'>")
    blocks = parse_blocks(html)
    imgs = [im for b in blocks for im in b.images]
    assert any(im.alt == "waterfall" for im in imgs)
    assert all(im.occurrences == 2 for im in imgs)


def test_session_title():
    assert session_title("<h1>My Session</h1><h2>x</h2>") == "My Session"
