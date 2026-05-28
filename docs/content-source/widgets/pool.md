# Pool Widget Options

Reads pool water temperature from an InfluxDB v2 server and cycles four screens: a title card, today's current temp with trend arrow and hi/lo, a 7-day mean with hi/lo, and a season (current-year) hi/lo. Requires `INFLUXDB_TOKEN` in your `.env` file.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `title` | string | `"POOL TEMPS"` | Label shown on the title screen. |
| `sensor_id` | string | none | Sensor ID to filter on. Omit to use the only or first sensor in the bucket. |
| `units` | string | `"imperial"` | `"imperial"` (°F) or `"metric"` (°C). |
| `update_interval` | int | `300` | Seconds between InfluxDB fetches. Default is 5 minutes. |
| `stale_after` | int | `900` | Seconds since the last reading before the temperature is shown in dim gray to indicate stale data. Default is 15 minutes. |
| `influxdb_url` | string | `$INFLUXDB_URL` or `"http://influxdb:8086"` | InfluxDB v2 base URL. Overrides the env var when set in config. |
| `influxdb_org` | string | `$INFLUXDB_ORG` or `"pool"` | InfluxDB organization name. Overrides the env var when set in config. |
| `influxdb_bucket` | string | `$INFLUXDB_BUCKET` or `"pool_temps"` | InfluxDB bucket name. Overrides the env var when set in config. |
