"""Stage 0.5 image-description tests (mock / heuristic — no network)."""

from tutorial_builder.ingest.image_describer import describe_images, _heuristic_worthy
from tutorial_builder.schemas import ImageRef


def test_heuristic_flags_concept_diagrams_animatable():
    concept = ImageRef(image_id="a", src="x.png", nearby_heading="Waterfall Model Lifecycle")
    decorative = ImageRef(image_id="b", src="logo.png", alt="company logo")
    assert _heuristic_worthy(concept) is True
    assert _heuristic_worthy(decorative) is False


def test_repeated_images_are_not_animatable():
    repeated = ImageRef(image_id="c", src="hdr.png", alt="architecture diagram", occurrences=5)
    assert _heuristic_worthy(repeated) is False


def test_describe_images_populates_every_image():
    assets = [
        ImageRef(image_id="img_01", src="missing-local.png", alt="agile flow diagram",
                 nearby_heading="Agile Model"),
        ImageRef(image_id="img_02", src="missing-local2.png", alt="team photo"),
    ]
    out = describe_images(assets)
    assert len(out) == 2
    for im in out:
        assert im.description                      # never empty
        assert im.animation_worthy is not None     # always decided
        assert im.description_source in ("mock", "heuristic", "vision")
    # the diagram is animatable; the photo is not
    assert out[0].animation_worthy is True
    assert out[1].animation_worthy is False
