<?php
/**
 * Plugin Name: BeTrendy Store
 * Description: BeTrendy shipping, invoice checkout and bounded administrator setup.
 * Version: 1.0.2
 * Requires PHP: 7.4
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }

function betrendy_store_target() {
    $allowed = array( 'betrendy.online', 'snow-anteater-890728.hostingersite.com' );
    return in_array( wp_parse_url( home_url(), PHP_URL_HOST ), $allowed, true )
        && in_array( wp_parse_url( get_option( 'home' ), PHP_URL_HOST ), $allowed, true );
}

add_action( 'wp_enqueue_scripts', function () {
    if ( betrendy_store_target() && ( is_cart() || is_checkout() ) ) {
        wp_enqueue_style( 'betrendy-delivery', plugins_url( 'delivery.css', __FILE__ ), array(), '1.0.2' );
    }
} );

add_action( 'woocommerce_shipping_init', function () {
    if ( ! betrendy_store_target() || class_exists( 'BeTrendy_Nova_Poshta' ) ) { return; }
    class BeTrendy_Nova_Poshta extends WC_Shipping_Method {
        public function __construct( $instance_id = 0 ) {
            $this->id = 'betrendy_nova_poshta';
            $this->instance_id = absint( $instance_id );
            $this->method_title = 'BeTrendy — Нова пошта';
            $this->method_description = 'Відділення, поштомат або кур’єр. До 1500 грн вартість доставки підтверджує менеджер за тарифами перевізника; від 1500 грн — безкоштовно.';
            $this->supports = array( 'shipping-zones', 'instance-settings' );
            $this->title = 'Нова пошта';
            $this->enabled = 'yes';
            $this->instance_form_fields = array();
            $this->init_settings();
        }
        public function calculate_shipping( $package = array() ) {
            if ( 'UA' !== ( $package['destination']['country'] ?? '' ) ) { return; }
            $subtotal = 0;
            foreach ( $package['contents'] ?? array() as $item ) { $subtotal += (float) ( $item['line_total'] ?? 0 ); }
            $free = $subtotal >= 1500;
            foreach ( array( 'branch' => 'відділення', 'locker' => 'поштомат', 'courier' => 'кур’єр' ) as $suffix => $label ) {
                $this->add_rate( array( 'id' => $this->get_rate_id( $suffix ),
                    'label' => 'Нова пошта — ' . $label . ( $free ? ' (безкоштовно)' : ' (тариф перевізника; суму підтвердить менеджер)' ),
                    'cost' => 0, 'taxes' => false, 'package' => $package,
                    'meta_data' => array( 'delivery_payment' => $free ? 'included' : 'delivery_cost_pending_confirmation' ) ) );
            }
        }
    }
} );
add_filter( 'woocommerce_shipping_methods', function ( $methods ) {
    if ( betrendy_store_target() ) { $methods['betrendy_nova_poshta'] = 'BeTrendy_Nova_Poshta'; }
    return $methods;
} );
add_action( 'woocommerce_init', function () {
    if ( ! betrendy_store_target() || ! function_exists( 'woocommerce_register_additional_checkout_field' ) ) { return; }
    woocommerce_register_additional_checkout_field( array(
        'id' => 'betrendy/delivery-point', 'label' => 'Номер відділення / поштомата або адреса кур’єрської доставки',
        'location' => 'order', 'type' => 'text', 'required' => true,
        'sanitize_callback' => 'sanitize_text_field',
    ) );
} );

final class BeTrendy_Store_Setup {
    const TYPE = 'betrendy_import';
    const REPORT = 'betrendy_store_report';
    public static function boot() {
        add_action( 'init', array( __CLASS__, 'register' ), 20 );
        add_action( 'rest_after_insert_' . self::TYPE, array( __CLASS__, 'command' ), 20, 3 );
    }
    public static function register() {
        register_post_meta( self::TYPE, 'betrendy_store_command', array( 'type' => 'string', 'single' => true, 'default' => '',
            'show_in_rest' => array( 'schema' => array( 'type' => 'string', 'enum' => array( '', 'inspect', 'configure', 'launch', 'verify', 'purge_cache' ) ) ),
            'auth_callback' => static function () { return current_user_can( 'manage_options' ); }, 'sanitize_callback' => 'sanitize_key' ) );
        register_post_meta( self::TYPE, self::REPORT, array( 'type' => 'string', 'single' => true, 'default' => '', 'show_in_rest' => true,
            'auth_callback' => static function () { return current_user_can( 'manage_options' ); } ) );
    }
    private static function check() {
        if ( ! betrendy_store_target() || ! class_exists( 'WooCommerce' ) || 'UAH' !== get_woocommerce_currency() ) {
            throw new RuntimeException( 'Only the verified BeTrendy WooCommerce store in UAH is supported.' );
        }
    }
    private static function products( $status = array( 'draft', 'publish' ) ) {
        return get_posts( array( 'post_type' => 'product', 'post_status' => $status, 'numberposts' => -1, 'fields' => 'ids',
            'meta_key' => '_betrendy_source_url', 'meta_compare' => 'EXISTS' ) );
    }
    private static function configure() {
        if ( 61 !== count( self::products() ) ) { throw new RuntimeException( 'Expected exactly 61 imported BeTrendy products.' ); }
        $id = (int) get_option( 'betrendy_shipping_zone_id', 0 );
        if ( ! $id && WC_Shipping_Zones::get_zones() ) { throw new RuntimeException( 'Existing shipping zones need review; none were overwritten.' ); }
        $settings = array( 'woocommerce_default_country' => 'UA', 'woocommerce_allowed_countries' => 'specific',
            'woocommerce_specific_allowed_countries' => array( 'UA' ), 'woocommerce_ship_to_countries' => 'specific',
            'woocommerce_specific_ship_to_countries' => array( 'UA' ), 'woocommerce_enable_guest_checkout' => 'yes',
            'woocommerce_terms_page_id' => 339, 'woocommerce_checkout_phone_field' => 'required' );
        if ( ! get_option( 'betrendy_store_before_setup' ) ) {
            $before = array(); foreach ( $settings as $key => $value ) { $before[ $key ] = get_option( $key ); }
            update_option( 'betrendy_store_before_setup', $before, false );
        }
        foreach ( $settings as $key => $value ) { update_option( $key, $value ); }
        $bacs = get_option( 'woocommerce_bacs_settings', array() );
        $bacs['enabled'] = 'yes'; $bacs['title'] = 'Оплата за рахунком після підтвердження';
        $bacs['description'] = 'Оформіть замовлення. Менеджер підтвердить наявність і надішле рахунок для оплати. Замовлення відправляється після надходження коштів.';
        $bacs['instructions'] = 'Дякуємо за замовлення! Дочекайтеся підтвердження менеджера та рахунку. У призначенні платежу вкажіть номер замовлення.';
        update_option( 'woocommerce_bacs_settings', $bacs );
        $zone = $id ? new WC_Shipping_Zone( $id ) : new WC_Shipping_Zone();
        if ( ! $id ) {
            $zone->set_zone_name( 'Україна — BeTrendy' ); $zone->set_zone_order( 0 ); $zone->add_location( 'UA', 'country' ); $id = $zone->save();
            update_option( 'betrendy_shipping_zone_id', $id, false );
        }
        $found = false;
        foreach ( $zone->get_shipping_methods() as $method ) { if ( 'betrendy_nova_poshta' === $method->id ) { $found = true; } }
        if ( ! $found ) { $instance = $zone->add_shipping_method( 'betrendy_nova_poshta' ); if ( ! $instance ) { throw new RuntimeException( 'Could not add the delivery method.' ); } }
        WC_Cache_Helper::get_transient_version( 'shipping', true );
        update_option( 'betrendy_store_configured', gmdate( 'c' ), false );
    }
    private static function launch() {
        if ( ! get_option( 'betrendy_store_configured' ) || 61 !== count( self::products( 'publish' ) ) ) { throw new RuntimeException( 'The store configuration and 61 published products are required.' ); }
        foreach ( array( 331, 332, 333, 334, 335, 336, 338, 339 ) as $id ) {
            if ( 'publish' !== get_post_status( $id ) || ! get_post_meta( $id, '_betrendy_source_url', true ) ) { throw new RuntimeException( 'A required source page/post is unpublished.' ); }
        }
        if ( 'page' !== get_option( 'show_on_front' ) || 333 !== (int) get_option( 'page_on_front' ) ) { throw new RuntimeException( 'The imported homepage must be assigned first.' ); }
        $blog = get_page_by_path( 'blog' );
        if ( ! $blog || 'publish' !== $blog->post_status ) { throw new RuntimeException( 'The blog page is missing.' ); }
        update_option( 'woocommerce_coming_soon', 'no' );
        flush_rewrite_rules( false );
        update_option( 'betrendy_store_launched', gmdate( 'c' ), false );
    }
    private static function inspect( $verify = false ) {
        $gateways = array(); foreach ( WC()->payment_gateways()->payment_gateways() as $key => $gateway ) {
            if ( 'yes' === $gateway->enabled ) { $gateways[] = array( 'id' => $key, 'title' => $gateway->get_title() ); }
        }
        $zones = array(); foreach ( WC_Shipping_Zones::get_zones() as $zone ) {
            $methods = array(); foreach ( $zone['shipping_methods'] as $method ) { $methods[] = array( 'id' => $method->id, 'enabled' => $method->enabled ); }
            $zones[] = array( 'id' => $zone['id'], 'name' => $zone['zone_name'], 'methods' => $methods );
        }
        $report = array( 'checked_at' => gmdate( 'c' ), 'site_url' => home_url(), 'currency' => get_woocommerce_currency(),
            'coming_soon' => get_option( 'woocommerce_coming_soon' ), 'country' => get_option( 'woocommerce_default_country' ),
            'front_page' => (int) get_option( 'page_on_front' ), 'posts_page' => (int) get_option( 'page_for_posts' ),
            'published_products' => count( self::products( 'publish' ) ), 'draft_products' => count( self::products( 'draft' ) ),
            'gateways' => $gateways, 'shipping_zones' => $zones,
            'configured_at' => get_option( 'betrendy_store_configured' ), 'launched_at' => get_option( 'betrendy_store_launched' ) );
        if ( $verify ) {
            WC()->shipping()->load_shipping_methods();
            if ( ! class_exists( 'BeTrendy_Nova_Poshta' ) ) { throw new RuntimeException( 'Delivery method is not registered.' ); }
            $package = array( 'destination' => array( 'country' => 'UA', 'state' => '', 'postcode' => '01001', 'city' => 'Київ' ) );
            $zone = WC_Shipping_Zones::get_zone_matching_package( $package );
            $method = null; foreach ( $zone->get_shipping_methods( true ) as $candidate ) {
                if ( 'betrendy_nova_poshta' === $candidate->id ) { $method = $candidate; break; }
            }
            if ( ! $method || $zone->get_id() !== (int) get_option( 'betrendy_shipping_zone_id' ) ) { throw new RuntimeException( 'The enabled BeTrendy shipping method must match the actual Ukrainian zone.' ); }
            $ids = self::products( 'publish' ); $product = wc_get_product( $ids[0] ?? 0 );
            if ( ! $product ) { throw new RuntimeException( 'A published product is required for the delivery tests.' ); }
            $tests = array(); foreach ( array( 1499, 1500 ) as $total ) {
                $package['contents'] = array( array( 'data' => $product, 'line_total' => $total, 'quantity' => 1 ) );
                $package['contents_cost'] = $total;
                $rates = $method->get_rates_for_package( $package );
                $labels = array(); foreach ( $rates as $rate ) { $labels[] = $rate->get_label(); }
                $expected = $total >= 1500 ? 'included' : 'delivery_cost_pending_confirmation';
                $correct = count( $rates ) === 3;
                foreach ( $rates as $rate ) { $meta = $rate->get_meta_data(); $correct = $correct && 0.0 === (float) $rate->get_cost() && $expected === ( $meta['delivery_payment'] ?? '' ); }
                $tests[] = array( 'subtotal' => $total, 'rates' => count( $rates ), 'labels' => $labels, 'passed' => $correct );
            }
            $report['shipping_boundary_tests'] = $tests;
            $report['passed'] = 61 === $report['published_products'] && 'no' === $report['coming_soon'] && 333 === $report['front_page']
                && in_array( 'bacs', array_column( $gateways, 'id' ), true ) && $tests[0]['passed'] && $tests[1]['passed'];
        }
        return $report;
    }
    public static function command( $post, $request, $creating ) {
        if ( ! current_user_can( 'manage_options' ) || $post->ID !== (int) get_option( 'betrendy_import_status_post' ) ) { return; }
        $meta = $request->get_param( 'meta' ); $command = is_array( $meta ) ? ( $meta['betrendy_store_command'] ?? '' ) : '';
        if ( ! in_array( $command, array( 'inspect', 'configure', 'launch', 'verify', 'purge_cache' ), true ) ) { return; }
        update_post_meta( $post->ID, 'betrendy_store_command', '' );
        try {
            self::check();
            if ( 'configure' === $command ) { self::configure(); }
            if ( 'launch' === $command ) { self::launch(); }
            if ( 'purge_cache' === $command ) {
                if ( ! defined( 'HOSTINGER_PLUGIN_REST_API_BASE' ) ) { throw new RuntimeException( 'Hostinger Tools is required for its supported cache purge.' ); }
                $response = rest_do_request( new WP_REST_Request( 'DELETE', '/' . trim( HOSTINGER_PLUGIN_REST_API_BASE, '/' ) . '/clear-cache' ) );
                $data = $response->get_data();
                if ( $response->get_status() !== 200 || empty( $data['data']['purged'] ) ) { throw new RuntimeException( 'Hostinger cache purge did not succeed: ' . wp_json_encode( $data ) ); }
            }
            $report = self::inspect( 'verify' === $command );
            if ( 'purge_cache' === $command ) { $report['hostinger_cache_purged'] = true; }
            $report['command'] = $command; $report['success'] = true;
        } catch ( Throwable $e ) { $report = array( 'success' => false, 'command' => $command, 'error' => $e->getMessage(), 'checked_at' => gmdate( 'c' ) ); }
        update_post_meta( $post->ID, self::REPORT, wp_json_encode( $report, JSON_UNESCAPED_UNICODE ) );
    }
}
BeTrendy_Store_Setup::boot();
