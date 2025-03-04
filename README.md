# Better driver for Waveshare 7.5" e-paper display

- saner API
- 4-grayscale with dithering for best looking grayscale images (supported by displays sold after 2024-10-23)
- fast thanks to numpy
- partial updates that actually work

## How fast is it?

Probably not as fast as a C driver, but a lot faster than the official Python driver.
Especially for 4-grayscale images.

Even when it's not much faster in terms of wall clock time, it's always much more efficient in terms of CPU time.

The original driver is particularly bad because it checks if the display is busy by constantly spinning a loop with no sleep, effectively causing 100% CPU usage during this time.
But even when patching this flaw, there are still many inefficiencies in data serialization, that I've been able to improve with numpy.

On a RaspberryPi Zero 2 W, number on the left is wall time, number on the right is CPU time:

| Update method   | Original driver | Patched orig. driver | This driver     |
|-----------------|-----------------|----------------------|-----------------|
| Grayscale       | 13.7 s / 13.9 s | 13.7 s / 11.9 s      | 2.66 s / 190 ms |
| Full bilevel    | 4.23 s / 3.90 s | 4.24 s / 419 ms      | 4.19 s / 266 ms |
| Fast bilevel    | 2.12 s / 1.72 s | 2.13 s / 295 ms      | 2.08 s / 153 ms |
| Partial bilevel | 965 ms / 622 ms | 971 ms / 234 ms      | 870 ms / 82 ms  |

> Patched orig. driver: simply the original driver with a short "sleep" in the "check display is busy" loop

(Oh and these 190 ms of CPU for a grayscale image? That's _with_ dithering, which doesn't exist in the original driver.)

## Usage

The original driver forces you to manually `init_X()` the display with the correct refresh method,
then transform the image to a "buffer" with the corresponding `getbuffer_X()` method,
and finally call the corresponding `display_X()` method.
And then you should not forget to call `sleep()` to de-energize the display.

That's very tedious and error-prone. This driver does all that for you with the help of context managers.

```python
import betterepd7in5
from PIL import Image

epd = betterepd7in5.EPD(betterepd7in5.RaspberryPi())

my_image = Image.open("my_image.png")

with epd.display_grayscale() as disp:
    disp(my_image)

with epd.display_bilevel_full_refresh() as disp:
    disp(my_image)

with epd.display_bilevel_fast_refresh() as disp:
    disp(my_image)

with epd.display_bilevel_partial_refresh() as disp:
    disp(my_image)
```

The context manager (`with ... as disp:`) automatically initializes the display,
and gives you a display function that takes a Pillow image that you can call as 
many times as you want.

When the context manager exits, it automatically puts the display to sleep,
unless you pass `sleep=False`. This can be useful to chain multiple display
methods one after the other without having to sleep in between (which takes
a couple of seconds).

```python
with epd.display_bilevel_full_refresh(sleep=False) as disp:
    disp(my_base_image)

with epd.display_bilevel_partial_refresh() as disp:
    for update in updates:
        disp(update)
```

You can also call `sleep()` and `clear()` as needed outside of a context.
