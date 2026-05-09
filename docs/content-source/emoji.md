Use `:slug:` inside any text-bearing widget to render a pixel-art icon inline. Each is an 8×8 sprite in its native colors; the surrounding text uses your `font_color`.

The slug list rots fast as new icons are added. The source of truth is `src/led_ticker/pixel_emoji.py` — `grep -E '^\s+"[a-z_]+":' src/led_ticker/pixel_emoji.py` lists every slug.

| Slug | Description | Hires variant |
|------|-------------|---------------|
| `:baseball:` | White ball with red stitching | yes |
| `:bunny:` | Bunny silhouette | yes |
| `:cat:` | Cat | yes |
| `:cloud:` | Cloud icon | yes |
| `:email:` | Envelope (white) | yes |
| `:flower:` | Pink flower | yes |
| `:fog:` | Fog icon | yes |
| `:heart:` | Heart | yes |
| `:instagram:` | Instagram glyph (magenta) | yes |
| `:moon:` | Crescent moon | yes |
| `:partly_cloudy:` | Sun + cloud | yes |
| `:pokeball:` | Pokeball | hires only — won't render at scale=1 |
| `:pride:` | Pride flag stripes | hires only |
| `:rain:` | Rain icon | yes |
| `:snow:` | Snow icon | yes |
| `:star:` | Yellow star | yes |
| `:sun:` | Sun icon | yes |
| `:taco:` | Taco | yes |
| `:thunder:` | Thunder icon | yes |

## Hires on the bigsign

When the panel is at `default_scale > 1`, slugs with a hires variant auto-render the higher-detail sprite — same horizontal footprint (8 logical columns), 16× more detail per cell. On `scale=1` (small sign), the lowres 8×8 sprite is used.

`:moon:` is the canonical hires example: 32×32 sprite with circle-subtraction shading. Hires-only slugs (`pokeball`, `pride`) render nothing on a small sign.

## Adding a new emoji

Edit `src/led_ticker/pixel_emoji.py`. Define an 8×8 pixel-data tuple (`(x, y, r, g, b)`), add it to `EMOJI_REGISTRY`. For hires, draw a 32×32 variant and add it to `HIRES_REGISTRY`. The renderer auto-handles the scale dispatch.
