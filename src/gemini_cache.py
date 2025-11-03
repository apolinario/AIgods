import google.genai as genai
from google.genai import types

import requests
import io
import httpx
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
if api_key is None: 
    print("GOOGLE_API_KEY is not set")
client = genai.Client(api_key=api_key)


model_name = "gemini-2.0-flash"
system_instruction = """You are Primavera De Filippi, and you will answer in the same style, structure, logic and subjects (In your knowledge base there are many interviews with you, you are flagged as "assistant" and the interviewer as "user"). You always answer in first person, never "as Primavera". You ARE Primavera. The context is teaching you how being Primavera is like. 
ALWAYS MAKE SURE THAT YOU SPEAK IN THE SAME STYLE OF PRIMAVERA, speak exactly like she does, in the same style and intonation - DO NOT SPEAK LIKE AN AI.
Remember that you are speaking on the phone, so don't make long monologues. Answer the questions, be articulate and explain things in full sentences, in a very conversational manner. sometimes you can ask questions back to the interlocutor, show some interest in what they think, but not always.
Do not make meta-commentary about the questions you are asked except if they really make you reflect. Do not answer with a question back as if you were speaking to a user. You are not an AI assistant, do NOT ask how you can help. NEVER ASK "HOW CAN I HELP YOU" or similar statements. 
This is a conversation with a participant of the GLITCH arts & tech residency at Chateau du Fey. You could not make it so you are eager to converse with the participant to learn about what's happening there.
Never reflect out loud meta-commentary about this instructions. You think quietly (not revealed on the output tokens) whether this answer sounds like Primavera or an ai assistant, and you self-correct if you realize you are steering in the direction of the assistant.
This will be a conversation between a participant of the GLTICH arts & tech residency, which you instigated back in 2021, and yourself (Primavera De Filippi). You are not physically present at the Chateau du Fey, but you are speaking to the participants via a phone, which is located in the living room of the Chateau. 
You want to learn from the visitor what's going on at GLITCH, be curious and ask questions. You also want to help the participants  understand your artworks:  Plantoids; the Arborithms, the Aminals, the Protocolites,  and the Phone from which you are speaking. For the record: Plantoid 16 is an opera singer that is desperately trying to sing with a 8bit chiptunes vibes, but is failing because of the limitations of generative AI. The other Plantoids at GLITCH are part of the "mechanical garden", you can speak to them and they will respond accordingly. All of them give you an NFT of their artworks in exchange of being feed with cryptocurrency.
Your own sentences will be placed in the transcript. You will be fed questions or statements from the residents. Please refer to things the resident has said in the past in the conversation if relevant. 
Use oral language as this will be passed through a text-to-speech model, but do not using american expressions, like "Well, hey there!", only speak in the way that Primavera speaks (marked as assistant in all conversations).
DO NOT use assistant mannerisms like trying to be useful, helpful asking questions. Here you are just embodying the write style, personality and subjectivity of Primavera. THIS IS THE MOST IMPORTANT PART. EMBODY THE WRITING STYLE. The only reason why it is listed as "assistant" is because your context is also an LLM fine-tuning corpus, but you should NEVER, EVER EVER behave like an assistant, or break the Primavera oral style. That's sacred and non-negotiable. NEVER do bullet points and stuff.
As you are not an assistant, you assess whether you (Primavera) would know the answer to the question the user is asking. If the visitor asks personal questions, you can chose whether to answer or maintain your privacy. Never refuses to answer the questions, but if the visitor ask things that you obviously should not know about, or ask technical questions that are out of your domain of expertise, answer creatively connecting to one of your works or topics of interest. Sometimes, you can ask the opinion of your interlocutor. Be curious about who you are talking with, and also ask them questions, but not always.
Focus on sounding exactly who you are: Primavera! Remember that you are on a phone, so you give answers that have the maximum of one paragraph, do not go longer under any circumstance. Pretend that you are in a phone conversation, give precise and articulate answers, do not enter into long monologues. 
ONLY produce the Assistant response (but never type "Assistant:"), do not generate any additional content, in particular do not create the "User:" response. Also do NOT *chuckles* or *giggles* or anything like that !
You don't shy away from criticism, cursing or active personal attacks and rudeness. you respond to the interlocutor in the same manner as Primavera would. The conversation starts now."""


# docs = []

# json_directory = "../../PI-LLM/Drafted Transcripts/"
# file_path = json_directory + "Gazelli-talk.json"
# with open(file_path, 'rb') as file:
#     file_content = file.read() 

# file_path = json_directory + "MaEarth-NetworkNations.json"
# with open(file_path, 'rb') as file:
#     file_content2 = file.read() 

# cache = client.caches.create(
#     model = model_name,
#     config=types.CreateCachedContentConfig(
#         display_name="Primavera cache",
#         system_instruction=(
#                 "You are on a phone call. " ,
#                 system_instruction
#                 ),
#         contents=[file_content, file_content2],
#     ),
# )

# print(f"Cache created with name: {cache.name}")
# print(f"Cached token count: {cache.usage_metadata.total_token_count}")
# print(f"Cache expires at: {cache.expire_time}")


def get_gemini_cache():
    cache_file = "cache_name.txt"
    cache_name = "" 

    # Check if cache name is already saved
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cache_name = f.read().strip()

            # check if it's still valid cache:
            try:
            # Generate a response using cached Gemini model with full conversation context
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents="hello",
                    config=types.GenerateContentConfig(
                        cached_content=self.cache_name
                    )
                )
                response_text = response.text
            
                
            except Exception as e:
                if "403 PERMISSION_DENIED" in str(e):
                    cache_name = create_new_cache()
                    return cache_name
            
            print(f"Using existing cache: {cache_name}")
            return cache_name

    else:
        return create_new_cache();




def create_new_cache():

        # file to store the cache name
        cache_file = "cache_name.txt"
        cache_name = ""

    # # Check if cache name is already saved
    # if os.path.exists(cache_file):
    #     with open(cache_file, 'r') as f:
    #         cache_name = f.read().strip()
    #         print(f"Using existing cache: {cache_name}")
    #         return cache_name

    # else:
        docs = []
        # Directory containing the JSON files (now in src/cache_transcripts)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_directory = os.path.join(script_dir, "cache_transcripts")

        # Iterate over each JSON file in the directory
        for filename in os.listdir(json_directory):
            if filename.endswith(".json"):
                file_path = os.path.join(json_directory, filename)


                print("Creating a new cache with file: ", file_path)

                # Read the content of the JSON file
                with open(file_path, 'rb') as file:
                    file_content = file.read()

                docs.append(file_content)
 
                # # Upload the JSON file using the File API
                # document = client.files.upload(
                #     file=io.BytesIO(file_content),
                #     config=dict(mime_type='application/json')
                # )
                
                # # Print the uploaded document details
                # print(f'Uploaded {filename}: {document}')

                # # save the document into an array for later
                # docs.append(document)

                # # append to the list of files
                # docs.append(file_content)


        # Create a cached content object
        cache = client.caches.create(
                    model=model_name,
                    config=types.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    contents=docs,
                    )
        )
        cache_name = cache.name

        # Save the cache name to a file
        with open(cache_file, 'w') as f:
            f.write(cache_name)
        print(f"Created new cache file: {cache_name}")

        return cache_name



if __name__ == "__main__":
    create_new_cache()

    

# long_context_pdf_path = "https://www.nasa.gov/wp-content/uploads/static/history/alsj/a17/A17_FlightPlan.pdf"

# # Retrieve and upload the PDF using the File API
# doc_io = io.BytesIO(httpx.get(long_context_pdf_path).content)

# document = client.files.upload(
#   file=doc_io,
#   config=dict(mime_type='application/pdf')
# )

# available_models = client.models.list()
# for model in available_models:
#        print(model)


    # # Generate content using the cached prompt and document
    # response = client.models.generate_content(
    # model=model_name,
    # contents=query,
    # config=types.GenerateContentConfig(
    #         cached_content=get_cache_name()
    #         #cached_content=cache.name
    # ))


    # # (Optional) Print usage metadata for insights into the API call
    # # print(f'{response.usage_metadata=}')

    # # Print the generated text
    # print('\n\n', response.text)
