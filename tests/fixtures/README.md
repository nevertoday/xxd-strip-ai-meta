# JPEG fixture

`oriented.jpg` is a self-generated 3×2 image of six asymmetric color blocks,
with EXIF orientation 6, a test Software tag, and an sRGB ICC profile. It uses
no external image assets. Tests need only the committed JPEG and ExifTool;
Pillow is needed only to regenerate it from the repository root:

```python
from PIL import Image, ImageCms

image = Image.new('RGB', (3, 2))
image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255),
               (255, 255, 0), (0, 255, 255), (255, 0, 255)])
exif = Image.Exif()
exif[274] = 6
exif[305] = 'orientation regression fixture'
profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
image.save('tests/fixtures/oriented.jpg', quality=95, exif=exif, icc_profile=profile)
```
