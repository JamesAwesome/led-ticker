Use `:slug:` inside any text-bearing widget to render a pixel-art icon inline. Each is an 8×8 sprite in its native colors; the surrounding text uses your `font_color`. On a `default_scale > 1` panel (bigsign), every slug with a Hires column below auto-upgrades to a 32×32 hires sprite — same horizontal footprint, 16× more detail. The fall & Halloween slugs further down upgrade to the standard-emoji pack's Noto glyph instead, except the three curated-only ones, which block-expand from 8×8.

The slug list rots fast as new icons are added. The source of truth is the registry itself — `uv run python -c 'from led_ticker.pixel_emoji import emoji_slugs; print(sorted(emoji_slugs()))'` lists every built-in slug (sprites live in `src/led_ticker/pixel_emoji.py` and `src/led_ticker/fall_emoji.py`). Re-run `uv run python tools/render_emoji_previews.py` after adding a sprite to refresh the previews on this page.

> **Plugin emoji.** Some icons ship with external plugins (install the plugin to use them; the slugs in the table below are all built in):
>
> - `:baseball.ball:` (white ball with red stitching) — [`baseball`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/baseball)
> - `:pokeball.ball:` (red top, white bottom, button-banded) — [`pokeball`](https://github.com/JamesAwesome/led-ticker-plugins/tree/main/plugins/pokeball)

| Slug | Lowres (8×8) | Hires (32×32) | Description |
|------|--------------|---------------|-------------|
| `:bunny:` | <img src="/emoji/bunny-low.png" width="64" alt="bunny lowres"> | <img src="/emoji/bunny-hi.png" width="64" alt="bunny hires"> | Bunny silhouette |
| `:cat:` | <img src="/emoji/cat-low.png" width="64" alt="cat lowres"> | <img src="/emoji/cat-hi.png" width="64" alt="cat hires"> | Cat (default gray; see color variants below) |
| `:cloud:` | <img src="/emoji/cloud-low.png" width="64" alt="cloud lowres"> | <img src="/emoji/cloud-hi.png" width="64" alt="cloud hires"> | Cloud icon |
| `:droplet:` | <img src="/emoji/droplet-low.png" width="64" alt="droplet lowres"> | <img src="/emoji/droplet-hi.png" width="64" alt="droplet hires"> | Water droplet (blue teardrop) |
| `:email:` | <img src="/emoji/email-low.png" width="64" alt="email lowres"> | <img src="/emoji/email-hi.png" width="64" alt="email hires"> | Envelope (white) |
| `:fire:` | <img src="/emoji/fire-low.png" width="64" alt="fire lowres"> | <img src="/emoji/fire-hi.png" width="64" alt="fire hires"> | Flame (orange body, white-hot core) |
| `:flower:` | <img src="/emoji/flower-low.png" width="64" alt="flower lowres"> | <img src="/emoji/flower-hi.png" width="64" alt="flower hires"> | Pink flower |
| `:fog:` | <img src="/emoji/fog-low.png" width="64" alt="fog lowres"> | <img src="/emoji/fog-hi.png" width="64" alt="fog hires"> | Fog icon |
| `:heart:` | <img src="/emoji/heart-low.png" width="64" alt="heart lowres"> | <img src="/emoji/heart-hi.png" width="64" alt="heart hires"> | Heart (default red; see color variants below) |
| `:instagram:` | <img src="/emoji/instagram-low.png" width="64" alt="instagram lowres"> | <img src="/emoji/instagram-hi.png" width="64" alt="instagram hires"> | Instagram glyph (magenta gradient) |
| `:moon:` | <img src="/emoji/moon-low.png" width="64" alt="moon lowres"> | <img src="/emoji/moon-hi.png" width="64" alt="moon hires"> | Crescent moon |
| `:partly_cloudy:` | <img src="/emoji/partly_cloudy-low.png" width="64" alt="partly_cloudy lowres"> | <img src="/emoji/partly_cloudy-hi.png" width="64" alt="partly_cloudy hires"> | Sun + cloud |
| `:pride:` | <img src="/emoji/pride-low.png" width="64" alt="pride lowres"> | <img src="/emoji/pride-hi.png" width="64" alt="pride hires"> | Pride flag stripes (default rainbow; see variants below) |
| `:rain:` | <img src="/emoji/rain-low.png" width="64" alt="rain lowres"> | <img src="/emoji/rain-hi.png" width="64" alt="rain hires"> | Rain icon |
| `:snow:` | <img src="/emoji/snow-low.png" width="64" alt="snow lowres"> | <img src="/emoji/snow-hi.png" width="64" alt="snow hires"> | Snow icon |
| `:star:` | <img src="/emoji/star-low.png" width="64" alt="star lowres"> | <img src="/emoji/star-hi.png" width="64" alt="star hires"> | Yellow star (default; see color variants below) |
| `:sun:` | <img src="/emoji/sun-low.png" width="64" alt="sun lowres"> | <img src="/emoji/sun-hi.png" width="64" alt="sun hires"> | Sun icon |
| `:taco:` | <img src="/emoji/taco-low.png" width="64" alt="taco lowres"> | <img src="/emoji/taco-hi.png" width="64" alt="taco hires"> | Taco |
| `:thunder:` | <img src="/emoji/thunder-low.png" width="64" alt="thunder lowres"> | <img src="/emoji/thunder-hi.png" width="64" alt="thunder hires"> | Thunder icon |

## Fall & Halloween (smallsign 8×8)

The standard-emoji pack below already covers the season at hires, but pack sprites strip on a scale-1 sign. These slugs carry a hand-drawn **8×8 lowres**, so they render on the smallsign too — same slug (or the unicode emoji) on both signs. On a scaled sign the hires is still the pack's Noto glyph; the three curated-only slugs (`:pumpkin:`, `:acorn:`, `:candy_corn:`) have no standard emoji and block-expand from 8×8 there.

| Slug | Unicode | Lowres (8×8) | Description |
|------|---------|--------------|-------------|
| `:maple_leaf:` | 🍁 | <img src="/emoji/maple_leaf-low.png" width="64" alt="maple_leaf lowres"> | Maple leaf (red-orange, lighter vein) |
| `:fallen_leaf:` | 🍂 | <img src="/emoji/fallen_leaf-low.png" width="64" alt="fallen_leaf lowres"> | Fallen leaf (tan, on the diagonal) |
| `:jack_o_lantern:` | 🎃 | <img src="/emoji/jack_o_lantern-low.png" width="64" alt="jack_o_lantern lowres"> | Jack-o'-lantern (yellow eyes, jagged grin) |
| `:pumpkin:` | — | <img src="/emoji/pumpkin-low.png" width="64" alt="pumpkin lowres"> | Plain ribbed pumpkin (no standard emoji; curated-only) |
| `:acorn:` | — | <img src="/emoji/acorn-low.png" width="64" alt="acorn lowres"> | Acorn (no standard emoji; curated-only) |
| `:red_apple:` | 🍎 | <img src="/emoji/red_apple-low.png" width="64" alt="red_apple lowres"> | Red apple with stem and leaf |
| `:mushroom:` | 🍄 | <img src="/emoji/mushroom-low.png" width="64" alt="mushroom lowres"> | Red cap, white spots |
| `:ear_of_corn:` | 🌽 | <img src="/emoji/ear_of_corn-low.png" width="64" alt="ear_of_corn lowres"> | Yellow cob, green husk |
| `:turkey:` | 🦃 | <img src="/emoji/turkey-low.png" width="64" alt="turkey lowres"> | Fan tail, brown body, red wattle |
| `:ghost:` | 👻 | <img src="/emoji/ghost-low.png" width="64" alt="ghost lowres"> | White sheet, wavy hem |
| `:bat:` | 🦇 | <img src="/emoji/bat-low.png" width="64" alt="bat lowres"> | Purple — a black bat would vanish on the panel |
| `:hot_beverage:` | ☕ | <img src="/emoji/hot_beverage-low.png" width="64" alt="hot_beverage lowres"> | Steaming white mug |
| `:candle:` | 🕯️ | <img src="/emoji/candle-low.png" width="64" alt="candle lowres"> | Lit pillar candle |
| `:candy:` | 🍬 | <img src="/emoji/candy-low.png" width="64" alt="candy lowres"> | Red wrapped sweet |
| `:candy_corn:` | — | <img src="/emoji/candy_corn-low.png" width="64" alt="candy_corn lowres"> | White / orange / yellow (no standard emoji; curated-only) |
| `:skull:` | 💀 | <img src="/emoji/skull-low.png" width="64" alt="skull lowres"> | Sockets, nose, toothy jaw |
| `:owl:` | 🦉 | <img src="/emoji/owl-low.png" width="64" alt="owl lowres"> | Tufted brown owl, tan belly |
| `:spider_web:` | 🕸️ | <img src="/emoji/spider_web-low.png" width="64" alt="spider_web lowres"> | Corner web |
| `:leafless_tree:` | 🪾 | <img src="/emoji/leafless_tree-low.png" width="64" alt="leafless_tree lowres"> | Bare branches |

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

### Star colors

`:star:` defaults to yellow. Six additional color slugs share the same shape:

| Slug | Lowres | Hires |
|------|--------|-------|
| `:star_red:` | <img src="/emoji/star_red-low.png" width="48" alt="star_red lowres"> | <img src="/emoji/star_red-hi.png" width="48" alt="star_red hires"> |
| `:star_orange:` | <img src="/emoji/star_orange-low.png" width="48" alt="star_orange lowres"> | <img src="/emoji/star_orange-hi.png" width="48" alt="star_orange hires"> |
| `:star_yellow:` | <img src="/emoji/star_yellow-low.png" width="48" alt="star_yellow lowres"> | <img src="/emoji/star_yellow-hi.png" width="48" alt="star_yellow hires"> |
| `:star_green:` | <img src="/emoji/star_green-low.png" width="48" alt="star_green lowres"> | <img src="/emoji/star_green-hi.png" width="48" alt="star_green hires"> |
| `:star_blue:` | <img src="/emoji/star_blue-low.png" width="48" alt="star_blue lowres"> | <img src="/emoji/star_blue-hi.png" width="48" alt="star_blue hires"> |
| `:star_purple:` | <img src="/emoji/star_purple-low.png" width="48" alt="star_purple lowres"> | <img src="/emoji/star_purple-hi.png" width="48" alt="star_purple hires"> |
| `:star_pink:` | <img src="/emoji/star_pink-low.png" width="48" alt="star_pink lowres"> | <img src="/emoji/star_pink-hi.png" width="48" alt="star_pink hires"> |

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
