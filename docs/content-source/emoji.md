Use `:slug:` inside any text-bearing widget to render a pixel-art icon inline. Each is an 8×8 sprite in its native colors; the surrounding text uses your `font_color`. On a `default_scale > 1` panel (bigsign), every slug auto-upgrades to a 32×32 hires sprite — same horizontal footprint, 16× more detail.

The slug list rots fast as new icons are added. The source of truth is `src/led_ticker/pixel_emoji.py` — `grep -E '^\s+"[a-z_]+":' src/led_ticker/pixel_emoji.py` lists every slug. Re-run `uv run python tools/render_emoji_previews.py` after adding a sprite to refresh the previews on this page.

| Slug | Lowres (8×8) | Hires (32×32) | Description |
|------|--------------|---------------|-------------|
| `:baseball:` | <img src="/emoji/baseball-low.png" width="64" alt="baseball lowres"> | <img src="/emoji/baseball-hi.png" width="64" alt="baseball hires"> | White ball with red stitching |
| `:bunny:` | <img src="/emoji/bunny-low.png" width="64" alt="bunny lowres"> | <img src="/emoji/bunny-hi.png" width="64" alt="bunny hires"> | Bunny silhouette |
| `:cat:` | <img src="/emoji/cat-low.png" width="64" alt="cat lowres"> | <img src="/emoji/cat-hi.png" width="64" alt="cat hires"> | Cat (default gray; see color variants below) |
| `:cloud:` | <img src="/emoji/cloud-low.png" width="64" alt="cloud lowres"> | <img src="/emoji/cloud-hi.png" width="64" alt="cloud hires"> | Cloud icon |
| `:email:` | <img src="/emoji/email-low.png" width="64" alt="email lowres"> | <img src="/emoji/email-hi.png" width="64" alt="email hires"> | Envelope (white) |
| `:flower:` | <img src="/emoji/flower-low.png" width="64" alt="flower lowres"> | <img src="/emoji/flower-hi.png" width="64" alt="flower hires"> | Pink flower |
| `:fog:` | <img src="/emoji/fog-low.png" width="64" alt="fog lowres"> | <img src="/emoji/fog-hi.png" width="64" alt="fog hires"> | Fog icon |
| `:heart:` | <img src="/emoji/heart-low.png" width="64" alt="heart lowres"> | <img src="/emoji/heart-hi.png" width="64" alt="heart hires"> | Heart (default red; see color variants below) |
| `:instagram:` | <img src="/emoji/instagram-low.png" width="64" alt="instagram lowres"> | <img src="/emoji/instagram-hi.png" width="64" alt="instagram hires"> | Instagram glyph (magenta gradient) |
| `:moon:` | <img src="/emoji/moon-low.png" width="64" alt="moon lowres"> | <img src="/emoji/moon-hi.png" width="64" alt="moon hires"> | Crescent moon |
| `:partly_cloudy:` | <img src="/emoji/partly_cloudy-low.png" width="64" alt="partly_cloudy lowres"> | <img src="/emoji/partly_cloudy-hi.png" width="64" alt="partly_cloudy hires"> | Sun + cloud |
| `:pokeball:` | <img src="/emoji/pokeball-low.png" width="64" alt="pokeball lowres"> | <img src="/emoji/pokeball-hi.png" width="64" alt="pokeball hires"> | Pokeball — red top, white bottom, button-banded |
| `:pride:` | <img src="/emoji/pride-low.png" width="64" alt="pride lowres"> | <img src="/emoji/pride-hi.png" width="64" alt="pride hires"> | Pride flag stripes (default rainbow; see variants below) |
| `:rain:` | <img src="/emoji/rain-low.png" width="64" alt="rain lowres"> | <img src="/emoji/rain-hi.png" width="64" alt="rain hires"> | Rain icon |
| `:snow:` | <img src="/emoji/snow-low.png" width="64" alt="snow lowres"> | <img src="/emoji/snow-hi.png" width="64" alt="snow hires"> | Snow icon |
| `:star:` | <img src="/emoji/star-low.png" width="64" alt="star lowres"> | <img src="/emoji/star-hi.png" width="64" alt="star hires"> | Yellow star |
| `:sun:` | <img src="/emoji/sun-low.png" width="64" alt="sun lowres"> | <img src="/emoji/sun-hi.png" width="64" alt="sun hires"> | Sun icon |
| `:taco:` | <img src="/emoji/taco-low.png" width="64" alt="taco lowres"> | <img src="/emoji/taco-hi.png" width="64" alt="taco hires"> | Taco |
| `:thunder:` | <img src="/emoji/thunder-low.png" width="64" alt="thunder lowres"> | <img src="/emoji/thunder-hi.png" width="64" alt="thunder hires"> | Thunder icon |

## Color variants

### Heart colors

`:heart:` defaults to red. Six additional color slugs share the same shape:

| Slug | Lowres | Hires |
|------|--------|-------|
| `:heart_red:` | <img src="/emoji/heart_red-low.png" width="48" alt="heart_red lowres"> | <img src="/emoji/heart_red-hi.png" width="48" alt="heart_red hires"> |
| `:heart_orange:` | <img src="/emoji/heart_orange-low.png" width="48" alt="heart_orange lowres"> | <img src="/emoji/heart_orange-hi.png" width="48" alt="heart_orange hires"> |
| `:heart_yellow:` | <img src="/emoji/heart_yellow-low.png" width="48" alt="heart_yellow lowres"> | <img src="/emoji/heart_yellow-hi.png" width="48" alt="heart_yellow hires"> |
| `:heart_green:` | <img src="/emoji/heart_green-low.png" width="48" alt="heart_green lowres"> | <img src="/emoji/heart_green-hi.png" width="48" alt="heart_green hires"> |
| `:heart_blue:` | <img src="/emoji/heart_blue-low.png" width="48" alt="heart_blue lowres"> | <img src="/emoji/heart_blue-hi.png" width="48" alt="heart_blue hires"> |
| `:heart_purple:` | <img src="/emoji/heart_purple-low.png" width="48" alt="heart_purple lowres"> | <img src="/emoji/heart_purple-hi.png" width="48" alt="heart_purple hires"> |
| `:heart_pink:` | <img src="/emoji/heart_pink-low.png" width="48" alt="heart_pink lowres"> | <img src="/emoji/heart_pink-hi.png" width="48" alt="heart_pink hires"> |

### Cat colors

`:cat:` defaults to gray with yellow eyes. Five other coats are available:

| Slug | Lowres | Hires |
|------|--------|-------|
| `:cat_gray:` | <img src="/emoji/cat_gray-low.png" width="48" alt="cat_gray lowres"> | <img src="/emoji/cat_gray-hi.png" width="48" alt="cat_gray hires"> |
| `:cat_orange:` | <img src="/emoji/cat_orange-low.png" width="48" alt="cat_orange lowres"> | <img src="/emoji/cat_orange-hi.png" width="48" alt="cat_orange hires"> |
| `:cat_white:` | <img src="/emoji/cat_white-low.png" width="48" alt="cat_white lowres"> | <img src="/emoji/cat_white-hi.png" width="48" alt="cat_white hires"> |
| `:cat_black:` | <img src="/emoji/cat_black-low.png" width="48" alt="cat_black lowres"> | <img src="/emoji/cat_black-hi.png" width="48" alt="cat_black hires"> |
| `:cat_brown:` | <img src="/emoji/cat_brown-low.png" width="48" alt="cat_brown lowres"> | <img src="/emoji/cat_brown-hi.png" width="48" alt="cat_brown hires"> |
| `:cat_cream:` | <img src="/emoji/cat_cream-low.png" width="48" alt="cat_cream lowres"> | <img src="/emoji/cat_cream-hi.png" width="48" alt="cat_cream hires"> |

### Pride flag variants

`:pride:` defaults to the rainbow flag. Other flags:

| Slug | Lowres | Hires |
|------|--------|-------|
| `:pride_rainbow:` | <img src="/emoji/pride_rainbow-low.png" width="48" alt="pride_rainbow lowres"> | <img src="/emoji/pride_rainbow-hi.png" width="48" alt="pride_rainbow hires"> |
| `:pride_trans:` | <img src="/emoji/pride_trans-low.png" width="48" alt="pride_trans lowres"> | <img src="/emoji/pride_trans-hi.png" width="48" alt="pride_trans hires"> |
| `:pride_bi:` | <img src="/emoji/pride_bi-low.png" width="48" alt="pride_bi lowres"> | <img src="/emoji/pride_bi-hi.png" width="48" alt="pride_bi hires"> |
| `:pride_lesbian:` | <img src="/emoji/pride_lesbian-low.png" width="48" alt="pride_lesbian lowres"> | <img src="/emoji/pride_lesbian-hi.png" width="48" alt="pride_lesbian hires"> |
| `:pride_nb:` | <img src="/emoji/pride_nb-low.png" width="48" alt="pride_nb lowres"> | <img src="/emoji/pride_nb-hi.png" width="48" alt="pride_nb hires"> |
| `:pride_ace:` | <img src="/emoji/pride_ace-low.png" width="48" alt="pride_ace lowres"> | <img src="/emoji/pride_ace-hi.png" width="48" alt="pride_ace hires"> |
| `:pride_demi:` | <img src="/emoji/pride_demi-low.png" width="48" alt="pride_demi lowres"> | <img src="/emoji/pride_demi-hi.png" width="48" alt="pride_demi hires"> |

## Hires on the bigsign

When the panel is at `default_scale > 1`, slugs auto-render the higher-detail sprite — same horizontal footprint (8 logical columns), 16× more detail per cell. On `scale=1` (small sign), the lowres 8×8 sprite is used.

`:moon:` is the canonical hires example: a 32×32 sprite with circle-subtraction shading.

## Adding a new emoji

Edit `src/led_ticker/pixel_emoji.py`. Define an 8×8 pixel-data tuple (`(x, y, r, g, b)`), add it to `EMOJI_REGISTRY`. For hires, draw a 32×32 variant and add it to `HIRES_REGISTRY`. The renderer auto-handles the scale dispatch. Then run `uv run python tools/render_emoji_previews.py` to refresh the preview PNGs.
