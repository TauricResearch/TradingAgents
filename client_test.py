from isek.node.etcd_registry import EtcdRegistry
from isek.node.node_v2 import Node
from isek.utils.log import LoggerManager
from isek.utils.print_utils import print_send_message_result, print_panel

LoggerManager.plain_mode()
EXAMPLE_REGISTRY_HOST = "47.236.116.81"
SERVER_NODE_ID = "TA_Agent_News"
SERVER_NODE_ID = "TA_Agent_Market"
SERVER_NODE_ID = "TA_Agent_Social"
# SERVER_NODE_ID = "TA_Agent_Fundamentals"

# Create the server node.
etcd_registry = EtcdRegistry(host=EXAMPLE_REGISTRY_HOST, port=2379)
client_node = Node(node_id="RN_client", port=8889, p2p=True, p2p_server_port=9001, registry=etcd_registry)

# Start the server in the foreground.
client_node.build_server(daemon=True)

print_panel(title="LV10 P2P Node Client",
            content="This Client accesses RN node through the p2p protocol."
            "\nAnd demonstrate the autonomous discovery of nodes through the registration center",
            color="bright_yellow")

print_send_message_result(
        lambda msg: client_node.send_message(SERVER_NODE_ID, msg),
        source_node_id=client_node.node_id,
        target_node_id=SERVER_NODE_ID,
        message="NVDA,2024-01-03"
    )

# reply = client_node.send_message("RN", "random a number 10-100")
# print(f"RN say:\n{reply}")
