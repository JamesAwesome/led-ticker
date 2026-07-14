// Cloudflare Pages Function: 301 the *.pages.dev default domain to the
// canonical host. Google indexed led-ticker.pages.dev (a full duplicate of
// the site) instead of docs.ledticker.dev; a canonical <link> is only a hint,
// so the duplicate must stop serving 200s. The exact-host check keeps PR
// preview deploys (<branch>.led-ticker.pages.dev) working — only the bare
// production default domain redirects.
//
// Wrangler picks this up automatically: `pages deploy` compiles a functions/
// directory sitting next to the deploy output (see docs-deploy.yml).

const PAGES_DEV_HOST = "led-ticker.pages.dev";
const CANONICAL_HOST = "docs.ledticker.dev";

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (url.hostname === PAGES_DEV_HOST) {
    url.hostname = CANONICAL_HOST;
    return Response.redirect(url.toString(), 301);
  }
  return context.next();
}
