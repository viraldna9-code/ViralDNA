import asyncio
import edge_tts

async def amain():
    ssml = """<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
  <voice name="en-US-ChristopherNeural">
    This is a test of the bilingual broadcast pipeline.
  </voice>
  <voice name="te-IN-MohanNeural">
    ఆంధ్ర ప్రదేశ్
  </voice>
  <voice name="en-US-ChristopherNeural">
    is a key region.
  </voice>
</speak>"""
    communicate = edge_tts.Communicate(ssml=ssml)
    # Note: Communicate can take ssml directly, but we need to see if it supports it in this version.
    # In some edge-tts versions, passing SSML is supported, in others we pass text.
    # Let's see if it works!
    await communicate.save("/home/jay/modules/test_ssml_out.mp3")
    print("SSML synthesis complete.")

if __name__ == "__main__":
    asyncio.run(amain())
