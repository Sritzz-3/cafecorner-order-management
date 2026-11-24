from abc import ABC, abstractmethod
import os
from pathlib import Path

from printer_client.formatter import format_coupon_slip, format_order_slip


class PrinterBackend(ABC):
    def __init__(self, width=42):
        if width not in (32, 42):
            raise ValueError("Receipt width must be 32 or 42 characters.")
        self.width = width

    @abstractmethod
    def print_order_slip(self, job):
        raise NotImplementedError

    @abstractmethod
    def print_coupon_slip(self, job):
        raise NotImplementedError

    def close(self):
        pass


class ConsolePrinter(PrinterBackend):
    def __init__(self, width=42, output_file="printed_slips.txt"):
        super().__init__(width=width)
        self.output_file = Path(output_file)

    def _emit(self, text):
        print(text, end="")
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with self.output_file.open("a", encoding="utf-8") as stream:
            stream.write(text)
            stream.write("\n" + ("=" * self.width) + "\n")

    def print_order_slip(self, job):
        self._emit(format_order_slip(job, self.width))

    def print_coupon_slip(self, job):
        self._emit(format_coupon_slip(job, self.width))


class ThermalPrinter(PrinterBackend):
    def __init__(self, device, width=42):
        super().__init__(width=width)
        self.device = device

    @classmethod
    def from_environment(cls, width=42, environ=None):
        values = os.environ if environ is None else environ
        from escpos.printer import Network, Usb

        vendor = values.get("THERMAL_USB_VENDOR_ID")
        product = values.get("THERMAL_USB_PRODUCT_ID")
        if vendor and product:
            device = Usb(int(vendor, 0), int(product, 0))
        else:
            host = values.get("THERMAL_NETWORK_HOST")
            if not host:
                raise ValueError("Set USB vendor/product IDs or THERMAL_NETWORK_HOST for the thermal backend.")
            port = int(values.get("THERMAL_NETWORK_PORT", "9100"))
            device = Network(host, port=port)
        return cls(device=device, width=width)

    def _emit(self, text):
        self.device.text(text)
        self.device.cut()

    def print_order_slip(self, job):
        self._emit(format_order_slip(job, self.width))

    def print_coupon_slip(self, job):
        self._emit(format_coupon_slip(job, self.width))

    def close(self):
        close = getattr(self.device, "close", None)
        if close:
            close()


def create_printer(backend="console", width=42, environ=None):
    values = os.environ if environ is None else environ
    if backend == "console":
        return ConsolePrinter(width=width, output_file=values.get("PRINTER_OUTPUT_FILE", "printed_slips.txt"))
    if backend == "thermal":
        return ThermalPrinter.from_environment(width=width, environ=values)
    raise ValueError("PRINTER_BACKEND must be 'console' or 'thermal'.")
