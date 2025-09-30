SCRAPER_CONFIG = {
    'max_concurrent': 15,
    'delay_between_requests': 0.1,
    'request_timeout': 30,
    'batch_size_multiplier': 2,
    'connection_pool_size': 50,
    'connections_per_host': 20,
    'dns_cache_ttl': 300,
    'max_retries': 3,
    'retry_backoff_factor': 0.5,
    'enable_caching': True,
    'cache_validation': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'verbose_logging': True,
    'show_progress': True,
}
PERFORMANCE_PRESETS = {
    'conservative': {
        'max_concurrent': 5,
        'delay_between_requests': 0.5,
        'request_timeout': 45,
        'max_retries': 5,
    },
    'balanced': {
        'max_concurrent': 15,
        'delay_between_requests': 0.1,
        'request_timeout': 30,
        'max_retries': 3,
    },
    'aggressive': {
        'max_concurrent': 30,
        'delay_between_requests': 0.05,
        'request_timeout': 20,
        'max_retries': 2,
    },
    'very_aggressive': {
        'max_concurrent': 50,
        'delay_between_requests': 0.02,
        'request_timeout': 15,
        'max_retries': 1,
    }
}
def get_config(preset='balanced'):
    config = SCRAPER_CONFIG.copy()
    if preset in PERFORMANCE_PRESETS:
        config.update(PERFORMANCE_PRESETS[preset])
    return config
def print_config_info():
    print("🔧 Scraper Configuration Guide")
    print("=" * 50)
    print()
    print("📊 Performance Presets:")
    for preset, settings in PERFORMANCE_PRESETS.items():
        print(f"  {preset:15} - {settings['max_concurrent']:2d} concurrent, {settings['delay_between_requests']:4.2f}s delay")
    print()
    print("⚙️  Key Parameters:")
    print("  max_concurrent        - Higher = faster but more server load")
    print("  delay_between_requests - Lower = faster but risk of being blocked")
    print("  request_timeout       - Balance between patience and speed")
    print("  max_retries          - Higher = more resilient but slower on failures")
    print()
    print("🎯 Recommendations:")
    print("  • Start with 'balanced' preset")
    print("  • Use 'conservative' if you get blocked or errors")
    print("  • Use 'aggressive' if server handles high load well")
    print("  • Monitor server response and adjust accordingly")
    print("  • Consider your internet connection speed")
if __name__ == "__main__":
    print_config_info()
