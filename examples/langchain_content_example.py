
import asyncio
import os
from scribe_ai.agents.content_creation_langchain import LangChainContentCreationSystem

async def main():
    # Initialize the system with your OpenAI API key
    system = LangChainContentCreationSystem(
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Create content
    topic = "The Impact of Artificial Intelligence on Healthcare"
    content = await system.create_content_with_research(topic)
    
    # Save the generated content
    with open("generated_content.md", "w") as f:
        f.write(content)

if __name__ == "__main__":
    asyncio.run(main())