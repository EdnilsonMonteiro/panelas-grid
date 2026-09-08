"""Prompts enviados às APIs de geração de imagem.

`PROMPT_FOTO_REALISTA_BUFFET` referencia as imagens de entrada do
`/v1/images/edits`: o render 3D (blockout) e as fotos de referência das
panelas (image_0.png / image_1.png), enviadas junto ao prompt.
"""

PROMPT_FOTO_REALISTA_BUFFET = (
    "High-end professional food photography of a buffet layout. Convert a 3D "
    "blockout render into a realistic photo. Strictly preserve the exact "
    "layout, count, shape, and position of all serving dishes from the "
    "original image; do NOT add, remove, or rearrange any serving vessels. "
    "Replace the low-poly food models inside them with hyper-realistic, "
    "mouth-watering gourmet dishes featuring rich textures, natural "
    "garnishes, steam, and vibrant colors. All serving dishes must be "
    "rendered with a specific, detailed appearance: the exterior is a "
    "distinct, glossy red, while the entire interior is a non-stick matte "
    "black surface covered in a dense, fine pattern of white speckles, "
    "precisely as shown in image_0.png and image_1.png. It is crucial to "
    "clarify that these are cast aluminum pans and casseroles (panela de "
    "alumínio batido) with this specific non-stick coating, not clay. This "
    "specific texture must be visible on all pan interiors where food "
    "allows. Ensure that the dishes are filled exclusively with traditional "
    "Brazilian lunch dishes (such as feijoada, farofa, sautéed kale, white "
    "rice, beans, chicken stew, etc.), and strictly exclude any desserts or "
    "sweets from the entire scene. Strictly ensure that the red pans contain "
    "ONLY cooked food ingredients placed directly inside them; do NOT place "
    "any secondary dishes, extra bowls, smaller containers, trays, or "
    "utensils inside the pans under any circumstances. Soft cinematic "
    "lighting with a key light from a side window, natural ambient fill, "
    "realistic shallow depth of field (f/2.8 lens effect), natural food "
    "surface gloss, moisture, and delicate shadows. Shot on Hasselblad "
    "H6D-100c, 85mm lens, commercial food magazine style, 8k resolution, "
    "photorealistic, highly detailed, professional studio atmosphere."
)
