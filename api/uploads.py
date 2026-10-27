class UploadAdapter:
    def __init__(self, name, content_type, data):
        self.name = name
        self.type = content_type or ""
        self._data = data

    def getvalue(self):
        return self._data


async def adapt_upload(upload):
    return UploadAdapter(upload.filename or "file", upload.content_type, await upload.read())
