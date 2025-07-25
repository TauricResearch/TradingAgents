import chainlit as cl
import os
from dotenv import load_dotenv
from isek.node.node_v2 import Node
from isek.utils.log import log
from isek.node.etcd_registry import EtcdRegistry

# Load environment variables
load_dotenv()

# Server configuration
SERVER_NODE_ID = "TA_Agent"

# Global client node instance
client_node = None

@cl.on_chat_start
async def start():
    """Initialize the client connection to the ISEK server"""
    global client_node
    
    try:
        # Create a client node to send messages
        EXAMPLE_REGISTRY_HOST = "47.236.116.81"

        # Create the server node.
        etcd_registry = EtcdRegistry(host=EXAMPLE_REGISTRY_HOST, port=2379)
        client_node = Node(node_id="Lyra_client", port=8889, p2p=True, p2p_server_port=9001, registry=etcd_registry)
        # Start the server in the foreground.
        client_node.build_server(daemon=True)
        
        # example of agent card
        # • AdapterCard(name='SimpleAdapter', 
        #               bio='A simple adapter for testing', 
        #               lore='Created for testing purposes', 
        #               knowledge='Basic testing knowledge', 
        #               routine='Respond to messages')
        # Send welcome message
        await cl.Message(
            content=f"🤖 Welcome to ISEK Agent Interface!\n\n"
                   f"I'm connected to your ISEK agent server. You can now interact with the agent ",
            author="System"
        ).send()
    
        log.info("Chainlit client connected to ISEK server")
        
    except Exception as e:
        await cl.Message(
            content=f"❌ Failed to connect to ISEK server: {str(e)}\n\n"
                   "Please make sure the agent server is running on localhost:9006",
            author="System"
        ).send()
        log.error(f"Failed to connect to ISEK server: {e}")

@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages and forward them to the ISEK agent"""
    global client_node
    
    if client_node is None:
        await cl.Message(
            content="❌ Client not initialized. Please refresh the page.",
            author="System"
        ).send()
        return
    
    try:
        # Send message to ISEK agent and get response
        response = client_node.send_message(SERVER_NODE_ID, message.content)
        
        # Show agent response
        if response is not None:
            await cl.Message(
                content=str(response),
                author="ISEK Agent"
            ).send()
        else:
            await cl.Message(
                content="No response received from agent",
                author="System"
            ).send()
        
    except Exception as e:
        error_msg = f"❌ Error communicating with agent: {str(e)}"
        await cl.Message(
            content=error_msg,
            author="System"
        ).send()
        log.error(f"Error in message handling: {e}")

@cl.on_chat_end
async def end():
    """Clean up when chat ends"""
    global client_node
    client_node = None
    log.info("Chainlit client disconnected")

# Note: Chat profile configuration has been removed as it's not supported in current Chainlit version 