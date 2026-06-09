import asyncio
import edge_tts

async def amain():
    text = "This is a test of the bilingual news broadcast. Today, the Chief Minister of ఆంధ్ర ప్రదేశ్ made an important announcement in Hyderabad."
    # We use en-US-AndrewMultilingualNeural which is a modern multilingual voice
    communicate = edge_tts.Communicate(text, "en-US-AndrewMultilingualNeural")
    await communicate.save("/home/jay/modules/test_multilingual_out.mp3")
    print("Multilingual voice synthesis complete.")

if __name__ == "__main__":
    asyncio.run(amain())
