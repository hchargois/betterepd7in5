import logging
import time
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImagePalette
import spidev
import gpiozero


logger = logging.getLogger(__name__)


class RaspberryPi:
    # Pin definition
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18
    MOSI_PIN = 10
    SCLK_PIN = 11

    def __init__(self):
        self.SPI = spidev.SpiDev()
        self.GPIO_RST_PIN = gpiozero.LED(self.RST_PIN)
        self.GPIO_DC_PIN = gpiozero.LED(self.DC_PIN)
        self.GPIO_PWR_PIN = gpiozero.LED(self.PWR_PIN)
        self.GPIO_BUSY_PIN = gpiozero.Button(self.BUSY_PIN, pull_up=False)

    def digital_write(self, pin, value):
        if pin == self.RST_PIN:
            if value:
                self.GPIO_RST_PIN.on()
            else:
                self.GPIO_RST_PIN.off()
        elif pin == self.DC_PIN:
            if value:
                self.GPIO_DC_PIN.on()
            else:
                self.GPIO_DC_PIN.off()

    def digital_read_busy(self):
        return self.GPIO_BUSY_PIN.value

    def spi_writebytes(self, data):
        self.SPI.writebytes(data)

    def spi_writebytes2(self, data):
        self.SPI.writebytes2(data)

    def module_init(self):
        self.GPIO_PWR_PIN.on()
        # SPI device, bus = 0, device = 0
        self.SPI.open(0, 0)
        self.SPI.max_speed_hz = 4000000
        self.SPI.mode = 0b00

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.close()

        self.GPIO_RST_PIN.off()
        self.GPIO_DC_PIN.off()
        self.GPIO_PWR_PIN.off()
        logger.debug("close 5V, Module enters 0 power consumption ...")


# Display resolution
EPD_WIDTH = 800
EPD_HEIGHT = 480

GRAY1 = 0xFF  # white
GRAY2 = 0x80  # light gray
GRAY3 = 0x40  # dark gray
GRAY4 = 0x00  # black

logger = logging.getLogger(__name__)


def _sleep_ms(ms):
    time.sleep(ms / 1000)


class EPD:
    def __init__(
        self, epdcfg, reverse: bool = False, gray_levels: tuple[int, int] = (32, 64)
    ):
        """
        :param epdcfg: EPD configuration
        :param reverse: True for 180 degree rotation
        :param gray_levels: tuple of gray levels used for 4-gray dithering.
            Adjust if dithered image looks too dark or too light
        """
        self.epdcfg = epdcfg
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

        self.reverse = reverse
        self.gray_levels = gray_levels

    # Hardware reset
    def reset(self):
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 1)
        _sleep_ms(20)
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 0)
        _sleep_ms(2)
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 1)
        _sleep_ms(20)

    def _send_command(self, command):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 0)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes((command,))
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _send_data(self, data):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 1)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes((data,))
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _send_data2(self, data):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 1)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes2(data)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _read_busy(self):
        logger.debug("e-Paper busy")
        self._send_command(0x71)
        busy = self.epdcfg.digital_read_busy()
        n = 1
        while busy == 0:
            n += 1
            _sleep_ms(10)  # avoid CPU hog by spinning too fast
            self._send_command(0x71)
            busy = self.epdcfg.digital_read_busy()
        _sleep_ms(20)
        logger.debug(f"e-Paper busy release, checked {n} times")

    def _init(self):
        self.epdcfg.module_init()
        # EPD hardware init start
        self.reset()

        self._send_command(0x06)  # btst
        self._send_data(0x17)
        self._send_data(0x17)
        self._send_data(0x28)  # If an exception is displayed, try using 0x38
        self._send_data(0x17)

        self._send_command(0x01)  # POWER SETTING
        self._send_data(0x07)
        self._send_data(0x07)  # VGH=20V,VGL=-20V
        self._send_data(0x28)  # VDH=15V
        self._send_data(0x17)  # VDL=-15V

        self._send_command(0x04)  # POWER ON
        _sleep_ms(100)
        self._read_busy()

        self._send_command(0x00)  # PANNEL SETTING
        self._send_data(0x1F)  # KW-3f   KWR-2F	BWROTP 0f	BWOTP 1f

        self._send_command(0x61)  # tres
        self._send_data(0x03)  # source 800
        self._send_data(0x20)
        self._send_data(0x01)  # gate 480
        self._send_data(0xE0)

        self._send_command(0x15)
        self._send_data(0x00)

        # If the screen appears gray, use the annotated initialization command
        self._send_command(0x50)
        self._send_data(0x10)
        self._send_data(0x07)
        # self.send_command(0X50)
        # self.send_data(0x10)
        # self.send_data(0x17)
        # self.send_command(0X52)
        # self.send_data(0x03)

        self._send_command(0x60)  # TCON SETTING
        self._send_data(0x22)

    def _init_fast(self):
        self.epdcfg.module_init()
        # EPD hardware init start
        self.reset()

        self._send_command(0x00)  # PANNEL SETTING
        self._send_data(0x1F)  # KW-3f   KWR-2F	BWROTP 0f	BWOTP 1f

        # If the screen appears gray, use the annotated initialization command
        self._send_command(0x50)
        self._send_data(0x10)
        self._send_data(0x07)
        # self.send_command(0X50)
        # self.send_data(0x10)
        # self.send_data(0x17)
        # self.send_command(0X52)
        # self.send_data(0x03)

        self._send_command(0x04)  # POWER ON
        _sleep_ms(100)
        self._read_busy()  # waiting for the electronic paper IC to release the idle signal

        # Enhanced display drive(Add 0x06 command)
        self._send_command(0x06)  # Booster Soft Start
        self._send_data(0x27)
        self._send_data(0x27)
        self._send_data(0x18)
        self._send_data(0x17)

        self._send_command(0xE0)
        self._send_data(0x02)
        self._send_command(0xE5)
        self._send_data(0x5A)

    def _init_partial(self):
        self.epdcfg.module_init()
        # EPD hardware init start
        self.reset()

        self._send_command(0x00)  # PANNEL SETTING
        self._send_data(0x1F)  # KW-3f   KWR-2F	BWROTP 0f	BWOTP 1f

        self._send_command(0x04)  # POWER ON
        _sleep_ms(100)
        self._read_busy()  # waiting for the electronic paper IC to release the idle signal

        self._send_command(0xE0)
        self._send_data(0x02)
        self._send_command(0xE5)
        self._send_data(0x6E)

    # The feature will only be available on screens sold after 24/10/23
    def _init_4gray(self):
        self.epdcfg.module_init()
        # EPD hardware init start
        self.reset()

        self._send_command(0x00)  # PANNEL SETTING
        self._send_data(0x1F)  # KW-3f   KWR-2F	BWROTP 0f	BWOTP 1f

        self._send_command(0x50)
        self._send_data(0x10)
        self._send_data(0x07)

        self._send_command(0x04)  # POWER ON
        _sleep_ms(100)
        self._read_busy()  # waiting for the electronic paper IC to release the idle signal

        # Enhanced display drive(Add 0x06 command)
        self._send_command(0x06)  # Booster Soft Start
        self._send_data(0x27)
        self._send_data(0x27)
        self._send_data(0x18)
        self._send_data(0x17)

        self._send_command(0xE0)
        self._send_data(0x02)
        self._send_command(0xE5)
        self._send_data(0x5F)

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        if image.height > image.width:
            if not self.reverse:
                image = image.transpose(Image.Transpose.ROTATE_90)
            else:
                image = image.transpose(Image.Transpose.ROTATE_270)
        elif self.reverse:
            image = image.transpose(Image.Transpose.ROTATE_180)

        if image.height != self.height or image.width != self.width:
            image = image.resize((self.width, self.height))

        return image

    def _display(self, image: Image.Image, sleep_after: int):
        data = self._prepare_image(image).convert("1").tobytes()

        self._send_command(0x10)
        self._send_data2(data)

        data_inv = ~np.frombuffer(data, dtype=np.uint8)
        self._send_command(0x13)
        self._send_data2(data_inv)

        self._send_command(0x12)
        _sleep_ms(sleep_after)
        self._read_busy()

    def _display_full(self, image: Image.Image):
        self._display(image, 3000)

    def _display_fast(self, image: Image.Image):
        self._display(image, 1000)

    def _display_partial(self, image: Image.Image, xy: tuple[int, int] | None = None):
        if xy is None:
            image = self._prepare_image(image)
            xy = (0, 0)

        x, y = xy
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            logger.warning("invalid coordinates for partial update")
            return

        x = x // 8 * 8

        if (x + image.width) > self.width or (y + image.height) > self.height:
            image = image.crop((0, 0, self.width - x, self.height - y))

        width, height = image.size
        if width % 8 != 0:
            width = width // 8 * 8
            image = image.crop((0, 0, width, height))

        if width == 0 or height == 0:
            logger.warning("skipping empty partial update")
            return

        self._send_command(0x50)
        self._send_data(0xA9)
        self._send_data(0x07)

        self._send_command(0x91)  # This command makes the display enter partial mode
        self._send_command(0x90)  # resolution setting
        self._send_data2(x.to_bytes(2, "big"))
        self._send_data2((x + width - 1).to_bytes(2, "big"))
        self._send_data2(y.to_bytes(2, "big"))
        self._send_data2((y + height - 1).to_bytes(2, "big"))

        self._send_data(0x01)

        data = image.convert("1").tobytes()

        self._send_command(0x13)  # Write Black and White image to RAM
        self._send_data2(data)

        self._send_command(0x12)
        _sleep_ms(300)
        self._read_busy()

    def _dither_4gray(self, image: Image.Image) -> Image.Image:
        palette_colors = (0, self.gray_levels[0], self.gray_levels[1], 255)
        palette_colors = [x for x in palette_colors for _ in range(3)]
        palette = ImagePalette.ImagePalette("RGB", palette_colors)
        palette_img = Image.new("P", (0, 0), 0)
        palette_img.putpalette(palette)

        # dithering from L image doesn't work, need to convert to RGB
        p_image = image.convert("RGB").quantize(4, palette=palette_img)
        output_palette_colors = (GRAY4, GRAY3, GRAY2, GRAY1)
        output_palette_colors = [x for x in output_palette_colors for _ in range(3)]
        p_image.putpalette(ImagePalette.ImagePalette("RGB", output_palette_colors))
        return p_image.convert("L")

    def _display_4gray(self, image: Image.Image, dither: bool = True):
        image = self._prepare_image(image).convert("L")
        if dither:
            image = self._dither_4gray(image)
        pixels = np.asarray(image, dtype=np.uint8).reshape(-1)
        pixels = pixels >> 6

        strides = pixels.reshape(-1, 8)

        lsb_inv = ~(
            ((strides[:, 0] & 1) << 7)
            | ((strides[:, 1] & 1) << 6)
            | ((strides[:, 2] & 1) << 5)
            | ((strides[:, 3] & 1) << 4)
            | ((strides[:, 4] & 1) << 3)
            | ((strides[:, 5] & 1) << 2)
            | ((strides[:, 6] & 1) << 1)
            | (strides[:, 7] & 1)
        )

        msb_inv = ~(
            ((strides[:, 0] & 2) << 6)
            | ((strides[:, 1] & 2) << 5)
            | ((strides[:, 2] & 2) << 4)
            | ((strides[:, 3] & 2) << 3)
            | ((strides[:, 4] & 2) << 2)
            | ((strides[:, 5] & 2) << 1)
            | ((strides[:, 6] & 2))
            | (strides[:, 7] >> 1)
        )

        self._send_command(0x10)
        self._send_data2(lsb_inv)

        self._send_command(0x13)
        self._send_data2(msb_inv)

        self._send_command(0x12)
        _sleep_ms(1800)
        self._read_busy()

    def clear(self):
        self._init()
        self._send_command(0x10)
        self._send_data2([0xFF] * (self.width * self.height // 8))
        self._send_command(0x13)
        self._send_data2([0x00] * (self.width * self.height // 8))

        self._send_command(0x12)
        _sleep_ms(3500)
        self._read_busy()

    def sleep(self):
        self._send_command(0x50)
        self._send_data(0xF7)

        self._send_command(0x02)  # POWER_OFF
        self._read_busy()

        self._send_command(0x07)  # DEEP_SLEEP
        self._send_data(0xA5)

        _sleep_ms(2000)
        self.epdcfg.module_exit()

    @contextmanager
    def display_bilevel_full_refresh(self, sleep: bool = True):
        """Uses the slowest refresh method to display an image. This is the
        best method to eliminate all ghosting."""
        self._init()
        try:
            yield self._display_full
        finally:
            if sleep:
                self.sleep()

    @contextmanager
    def display_bilevel_fast_refresh(self, sleep: bool = True):
        """Uses a fast refresh method to display an image. Ghosting is usually
        not visible and since the refresh time is much faster than the full
        refresh method, this is the recommended method for normal use."""
        self._init_fast()
        try:
            yield self._display_fast
        finally:
            if sleep:
                self.sleep()

    @contextmanager
    def display_bilevel_partial_refresh(self, sleep: bool = True):
        """Uses the fastest refresh method to display an image. Ghosting will be
        visible, and it is not recommended to use partial update too many times
        without other refresh methods in between as it may damage the screen.

        Partial update is a bit of a misnomer since it can be used to update the
        whole screen just like all other display methods. Just send an image
        and the whole screen will update, using auto-sizing and auto-rotation
        like the other display methods.

        Partial update can also be used to partially update the display using
        a smaller "patch" image. For that case, the display method has an extra
        paramter, xy, which should be the top-left corner of where the patch
        should be displayed. No auto-sizing and auto-rotation will happen in
        that case. Moreover, the width of the patch must be a multiple of 8
        pixels; and the x position must also be a multiple of 8. If they're not,
        they will be rounded down to the nearest multiple of 8.

        Note that "patch" partial-updates are slightly faster than "full-screen"
        partial-updates, but this is not linear with the patch size, e.g. it may
        take 0.7s to partial-update the whole display and 0.5s to partial-update
        even a tiny patch. Therefore in most cases you should just use full
        updates as they'll be more convenient.
        """
        self._init_partial()
        try:
            yield self._display_partial
        finally:
            if sleep:
                self.sleep()

    @contextmanager
    def display_grayscale(self, sleep: bool = True):
        """Uses 4-grayscale mode. Dithering is enabled by default, it can be
        turned off by setting dither=False in the display method.
        """
        self._init_4gray()
        try:
            yield self._display_4gray
        finally:
            if sleep:
                self.sleep()
