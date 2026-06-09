import asyncio
import edge_tts
import edge_tts.communicate
import aiohttp
import ssl
import certifi

# Original mkssml
orig_mkssml = edge_tts.communicate.mkssml

# Monkeypatch mkssml to return raw SSML if it is detected
def custom_mkssml(tc, escaped_text):
    if isinstance(escaped_text, bytes):
        escaped_text = escaped_text.decode("utf-8")
    if escaped_text.strip().startswith("<speak"):
        return escaped_text
    return orig_mkssml(tc, escaped_text)

edge_tts.communicate.mkssml = custom_mkssml

class CustomCommunicate(edge_tts.Communicate):
    def __init__(self, ssml_text: str, **kwargs):
        super().__init__(text="dummy", **kwargs)
        cleaned = edge_tts.communicate.remove_incompatible_characters(ssml_text)
        self.texts = list(edge_tts.communicate.split_text_by_byte_length(cleaned.encode("utf-8"), 4096))

class CustomRequestContextManager:
    def __init__(self, context_manager):
        self.cm = context_manager
        self.ws = None

    async def __aenter__(self):
        self.ws = await self.cm.__aenter__()
        
        orig_send_str = self.ws.send_str
        async def custom_send_str(s):
            print("WS SENT:\n", s)
            await orig_send_str(s)
        self.ws.send_str = custom_send_str
        
        # Patch __anext__ to show responses
        orig_anext = self.ws.__anext__
        async def custom_anext():
            try:
                msg = await orig_anext()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    print("WS RECV TEXT:\n", msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    print(f"WS RECV BINARY ({len(msg.data)} bytes)")
                return msg
            except Exception as e:
                print("WS RECV EXCEPTION:", e)
                raise
        self.ws.__anext__ = custom_anext
        
        return self.ws

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.cm.__aexit__(exc_type, exc_val, exc_tb)

orig_ws_connect = aiohttp.ClientSession.ws_connect
def custom_ws_connect(self, *args, **kwargs):
    cm = orig_ws_connect(self, *args, **kwargs)
    return CustomRequestContextManager(cm)

aiohttp.ClientSession.ws_connect = custom_ws_connect

async def amain():
    # Single-voice simple SSML test
    ssml = """<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
  <voice name="en-US-ChristopherNeural">
    <prosody rate="+0%">This is a single voice custom SSML test.</prosody>
  </voice>
</speak>"""
    
    communicate = CustomCommunicate(ssml)
    try:
        await communicate.save("/home/jay/modules/test_custom_ssml_out.mp3")
        print("SSML synthesis complete using custom monkeypatch!")
    except Exception as e:
        print("Main Exception caught:", e)

if __name__ == "__main__":
    asyncio.run(amain())
