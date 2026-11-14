# BeTrendy block theme

Native block theme for WordPress 6.6+ and WooCommerce. The importer supplies page content, products and media; the theme only supplies presentation.

## Installation

1. Install and configure WooCommerce on the separate BeTrendy WordPress site.
2. Upload the `betrendy` theme directory (or a ZIP with that directory at its root) and activate it.
3. Set the site title to Be Trendy and assign the imported logo in the Site Editor. The site title is used when no logo is set.
4. Import the pages and product catalogue. Assign the imported homepage in Settings → Reading.
5. Review the header and footer in Appearance → Editor. Their navigation uses the original category and information-page paths. The cart link uses `/cart/` and the 404 page uses `/shop/`.

## Editable content

Templates and template parts use registered WordPress core and WooCommerce blocks. The homepage template renders `core/post-content`, so its banners and sections remain editable in the page editor. No media IDs, menu post IDs or product IDs are hard-coded.

The theme supplies editable single-product and product-archive templates using native WooCommerce blocks. WooCommerce supplies cart and checkout behavior and owns all purchasing behavior. This theme declares WooCommerce support and styles both classic and block product output. It does not implement payment, shipping, stock or order logic.

Source appearance: Geologica, white background, dark `#2F3039` text, `#0D28D9` primary blue and `#D41D1D` sale red. Geologica loads from the same Google Fonts family used by the source site, with Arial/Helvetica fallbacks. The layout adapts for narrow screens and supports keyboard focus and reduced-motion preferences.

## Migration integration

- Information pages and category landing pages must exist at the source paths used by navigation, or the importer must rewrite the navigation links to their new routes.
- `/ru/` and `/en/` language links are temporarily omitted until their corresponding homepages and localized navigation work. Saved translation data is retained separately. Theme text is Ukrainian; translated header/footer template parts or a multilingual plugin are required for full navigation localization.
- The free-delivery banner preserves the source site's “Від 1500 грн безкоштовна доставка”. It is display text; the corresponding shipping rule must be configured in WooCommerce before launch.
- WooCommerce page selection, gateways and shipping need runtime verification on the target installation. No WordPress or WooCommerce runtime is bundled with this theme.

Source reviewed on 2026-11-13: https://betrendy.space/.

## Version 0.1.4 — 2026-11-14

The homepage carousel progressively enhances the existing editable image blocks with previous/next controls, labelled pagination and a slide counter. It supports native touch scrolling, arrow/Home/End keys, reduced motion and inert inactive slides; it does not autoplay. If JavaScript fails, the original horizontal image links remain available. The script loads only on the front page. Image attachment IDs let WordPress emit intrinsic dimensions and responsive sources.

About-page styling is scoped to `.bt-about`. Its updated core-block content and the current homepage are in `../../content/about.html` and `../../content/home.html`; restore these over the historical import content when rebuilding the site. Attachment IDs in these live snapshots belong to betrendy.online and must be remapped for another installation.
