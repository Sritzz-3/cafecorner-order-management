# CafeCorner printer client

This standalone Python script polls CafeCorner's print-job API. It uses `requests` and does not import Django. Console mode is the development/demo backend; `python-escpos` is an optional dependency for thermal printers.

## Run on macOS in console mode

From the repository root, with the project venv active, create a printer identity and copy its one-time token. Then create a separate venv for the standalone client:

```sh
source .venv/bin/activate
python manage.py create_printer_user
deactivate
python3 -m venv printer_client/.venv
source printer_client/.venv/bin/activate
python -m pip install -r printer_client/requirements.txt
export API_URL=http://127.0.0.1:8000/api
export PRINTER_TOKEN='paste-the-one-time-token-here'
export PRINTER_BACKEND=console
export POLL_INTERVAL=5
python printer_client/client.py
```

Console slips are printed in the terminal and appended to `printed_slips.txt`. The token is a secret; keep it out of source control and shell history when possible. The server returns a pending job only to the printer role, and the client claims it before printing.

Optional settings:

- `RECEIPT_WIDTH=32` or `42` (default `42`)
- `PRINTER_OUTPUT_FILE=/path/to/slips.txt`
- `LOG_LEVEL=INFO`
- `PRINTER_BACKEND=thermal` with either `THERMAL_USB_VENDOR_ID` and `THERMAL_USB_PRODUCT_ID` (IDs may use `0x` notation), or `THERMAL_NETWORK_HOST` and optional `THERMAL_NETWORK_PORT`

For a thermal backend, install the optional dependency with `python -m pip install -r printer_client/requirements-thermal.txt`.

## Raspberry Pi systemd example

Install the project and printer-client dependencies in a virtual environment on the Pi. Store `API_URL`, `PRINTER_TOKEN`, backend selection, and device settings in `/etc/cafecorner-printer.env`, owned by root and readable only by the service account. Then create `/etc/systemd/system/cafecorner-printer.service`:

```ini
[Unit]
Description=CafeCorner receipt printer client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cafecorner-printer
WorkingDirectory=/opt/cafecorner
EnvironmentFile=/etc/cafecorner-printer.env
ExecStart=/opt/cafecorner/printer_client/.venv/bin/python /opt/cafecorner/printer_client/client.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable it with `sudo systemctl daemon-reload`, `sudo systemctl enable --now cafecorner-printer`, and inspect logs with `sudo journalctl -u cafecorner-printer -f`.

## Hardware status

The ConsolePrinter backend and mocked API flow run in development. **The ThermalPrinter backend and ESC/POS device configuration have not been tested on real hardware.**

## Client tests

Run `python -m unittest discover -s printer_client/tests` from the repository root.
