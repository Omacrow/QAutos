import itertools

from sqa.ingestion.chunking import chunk_blocks
from sqa.ingestion.types import Block


def _sentences(n: int, word: str = "control") -> str:
    return " ".join(f"Sentence {i} describes the {word} in detail." for i in range(n))


def test_chunks_never_cross_sections() -> None:
    blocks = [
        Block("Access is reviewed quarterly.", page=1, heading_path=("Access",)),
        Block("Data is encrypted.", page=1, heading_path=("Encryption",)),
        Block("Keys rotate yearly.", page=2, heading_path=("Encryption",)),
    ]
    chunks = chunk_blocks(blocks)
    assert [(c.heading, c.text, c.page_start, c.page_end) for c in chunks] == [
        ("Access", "Access is reviewed quarterly.", 1, 1),
        ("Encryption", "Data is encrypted.\nKeys rotate yearly.", 1, 2),
    ]
    assert [c.ordinal for c in chunks] == [0, 1]


def test_long_sections_split_near_target_with_overlap() -> None:
    blocks = [Block(_sentences(6), page=p, heading_path=("Policy",)) for p in range(1, 9)]
    chunks = chunk_blocks(blocks, target_chars=800, max_chars=1200, overlap_chars=120)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1200 for c in chunks)
    assert all(c.heading == "Policy" for c in chunks)
    # Each chunk after the first repeats the tail of the one before it.
    for previous, current in itertools.pairwise(chunks):
        first_line = current.text.split("\n")[0]
        assert previous.text.endswith(first_line)
    # Page ranges are contiguous and cover every page.
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 8


def test_oversized_block_is_split_at_sentences() -> None:
    text = _sentences(60)
    chunks = chunk_blocks([Block(text, page=3)], target_chars=500, max_chars=600)
    assert all(len(c.text) <= 600 for c in chunks)
    assert all(c.page_start == c.page_end == 3 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)
    assert chunks[0].heading is None


def test_a_single_huge_sentence_is_hard_split() -> None:
    chunks = chunk_blocks([Block("word " * 1000, page=1)], max_chars=500, overlap_chars=0)
    assert all(len(c.text) <= 500 for c in chunks)
    assert sum(c.text.count("word") for c in chunks) == 1000


def test_spreadsheet_rows_keep_row_ranges_and_do_not_overlap() -> None:
    rows = [
        Block(
            f"Question: q{i} | Answer: {'yes ' * 20}", sheet="CAIQ", row=i, heading_path=("CAIQ",)
        )
        for i in range(2, 30)
    ]
    chunks = chunk_blocks(rows, sheet_target_chars=300)
    assert len(chunks) > 3
    covered = [r for c in chunks for r in range(c.row_start or 0, (c.row_end or 0) + 1)]
    assert covered == list(range(2, 30))  # every row exactly once
    assert all(c.sheet == "CAIQ" and c.page_start is None for c in chunks)


def test_short_tail_is_folded_into_previous_chunk() -> None:
    blocks = [
        Block(_sentences(10), page=1, heading_path=("A",)),
        Block("Short end.", page=2, heading_path=("A",)),
    ]
    chunks = chunk_blocks(blocks, target_chars=400, max_chars=2000, overlap_chars=0)
    assert chunks[-1].text.endswith("Short end.")
    assert len(chunks[-1].text) > len("Short end.")
    assert chunks[-1].page_end == 2


def test_empty_input() -> None:
    assert chunk_blocks([]) == []
