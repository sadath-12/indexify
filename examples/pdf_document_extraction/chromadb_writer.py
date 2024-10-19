from indexify.functions_sdk.indexify_functions import IndexifyFunction
from indexify import Image
from typing import Union
from common_objects import ImageWithEmbedding, TextChunk

image = Image(python="3.11").name("tensorlake/blueprints-chromadb").run("pip install chromadb").run("pip install pillow")

class ChromaDBWriter(IndexifyFunction):
    name = "chroma_db_writer"
    image = image

    def __init__(self):
        import chromadb
        super().__init__()
        self._client = chromadb.HttpClient(host="chromadb", port=8000)
        self._text_collection = self._client.create_collection(name="text_embeddings", metadata={"hnsw:space": "cosine"}, get_or_create=True)
        self._image_collection = self._client.create_collection(name="image_embeddings", metadata={"hnsw:space": "cosine"}, get_or_create=True)

    def run(self, input: Union[ImageWithEmbedding, TextChunk]) -> bool:
        import uuid
        from PIL import Image
        import io
        import numpy as np
        if type(input) == ImageWithEmbedding:
            img_arr = np.array(Image.open(io.BytesIO(input.image_bytes)))
            self._image_collection.add(
                ids=[str(uuid.uuid4())],
                embeddings=[input.embedding],
                metadatas=[{"page_number": input.page_number}],
                images=[img_arr]
            )
        elif type(input) == TextChunk:
            self._text_collection.add(
                ids=[str(uuid.uuid4())],
                embeddings=[input.embeddings],
                metadatas=[{"page_number": input.page_number}],
                documents=[input.chunk]
            )
        return True
