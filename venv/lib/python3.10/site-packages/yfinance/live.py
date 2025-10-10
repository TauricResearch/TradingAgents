import asyncio
import base64
import json
from typing import List, Optional, Callable, Union

from websockets.sync.client import connect as sync_connect
from websockets.asyncio.client import connect as async_connect

from yfinance import utils
from yfinance.pricing_pb2 import PricingData
from google.protobuf.json_format import MessageToDict


class BaseWebSocket:
    def __init__(self, url: str = "wss://streamer.finance.yahoo.com/?version=2", verbose=True):
        self.url = url
        self.verbose = verbose
        self.logger = utils.get_yf_logger()
        self._ws = None
        self._subscriptions = set()
        self._subscription_interval = 15  # seconds

    def _decode_message(self, base64_message: str) -> dict:
        try:
            decoded_bytes = base64.b64decode(base64_message)
            pricing_data = PricingData()
            pricing_data.ParseFromString(decoded_bytes)
            return MessageToDict(pricing_data, preserving_proto_field_name=True)
        except Exception as e:
            self.logger.error("Failed to decode message: %s", e, exc_info=True)
            if self.verbose:
                print("Failed to decode message: %s", e)
            return {
                'error': str(e),
                'raw_base64': base64_message
            }


class AsyncWebSocket(BaseWebSocket):
    """
    Asynchronous WebSocket client for streaming real time pricing data.
    """

    def __init__(self, url: str = "wss://streamer.finance.yahoo.com/?version=2", verbose=True):
        """
        Initialize the AsyncWebSocket client.

        Args:
            url (str): The WebSocket server URL. Defaults to Yahoo Finance's WebSocket URL.
            verbose (bool): Flag to enable or disable print statements. Defaults to True.
        """
        super().__init__(url, verbose)
        self._message_handler = None  # Callable to handle messages
        self._heartbeat_task = None  # Task to send heartbeat subscribe

    async def _connect(self):
        try:
            if self._ws is None:
                self._ws = await async_connect(self.url)
                self.logger.info("Connected to WebSocket.")
                if self.verbose:
                    print("Connected to WebSocket.")
        except Exception as e:
            self.logger.error("Failed to connect to WebSocket: %s", e, exc_info=True)
            if self.verbose:
                print(f"Failed to connect to WebSocket: {e}")
            self._ws = None
            raise

    async def _periodic_subscribe(self):
        while True:
            try:
                await asyncio.sleep(self._subscription_interval)

                if self._subscriptions:
                    message = {"subscribe": list(self._subscriptions)}
                    await self._ws.send(json.dumps(message))

                    if self.verbose:
                        print(f"Heartbeat subscription sent for symbols: {self._subscriptions}")
            except Exception as e:
                self.logger.error("Error in heartbeat subscription: %s", e, exc_info=True)
                if self.verbose:
                    print(f"Error in heartbeat subscription: {e}")
                break

    async def subscribe(self, symbols: Union[str, List[str]]):
        """
        Subscribe to a stock symbol or a list of stock symbols.

        Args:
            symbols (Union[str, List[str]]): Stock symbol(s) to subscribe to.
        """
        await self._connect()

        if isinstance(symbols, str):
            symbols = [symbols]

        self._subscriptions.update(symbols)

        message = {"subscribe": list(self._subscriptions)}
        await self._ws.send(json.dumps(message))

        # Start heartbeat subscription task
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._periodic_subscribe())

        self.logger.info(f"Subscribed to symbols: {symbols}")
        if self.verbose:
            print(f"Subscribed to symbols: {symbols}")

    async def unsubscribe(self, symbols: Union[str, List[str]]):
        """
        Unsubscribe from a stock symbol or a list of stock symbols.

        Args:
            symbols (Union[str, List[str]]): Stock symbol(s) to unsubscribe from.
        """
        await self._connect()

        if isinstance(symbols, str):
            symbols = [symbols]

        self._subscriptions.difference_update(symbols)

        message = {"unsubscribe": symbols}
        await self._ws.send(json.dumps(message))

        self.logger.info(f"Unsubscribed from symbols: {symbols}")
        if self.verbose:
            print(f"Unsubscribed from symbols: {symbols}")

    async def listen(self, message_handler=None):
        """
        Start listening to messages from the WebSocket server.

        Args:
            message_handler (Optional[Callable[[dict], None]]): Optional function to handle received messages.
        """
        await self._connect()
        self._message_handler = message_handler

        self.logger.info("Listening for messages...")
        if self.verbose:
            print("Listening for messages...")

        # Start heartbeat subscription task
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._periodic_subscribe())

        while True:
            try:
                async for message in self._ws:
                    message_json = json.loads(message)
                    encoded_data = message_json.get("message", "")
                    decoded_message = self._decode_message(encoded_data)

                    if self._message_handler:
                        try:
                            if asyncio.iscoroutinefunction(self._message_handler):
                                await self._message_handler(decoded_message)
                            else:
                                self._message_handler(decoded_message)
                        except Exception as handler_exception:
                            self.logger.error("Error in message handler: %s", handler_exception, exc_info=True)
                            if self.verbose:
                                print("Error in message handler:", handler_exception)
                    else:
                        print(decoded_message)

            except (KeyboardInterrupt, asyncio.CancelledError):
                self.logger.info("WebSocket listening interrupted. Closing connection...")
                if self.verbose:
                    print("WebSocket listening interrupted. Closing connection...")
                await self.close()
                break

            except Exception as e:
                self.logger.error("Error while listening to messages: %s", e, exc_info=True)
                if self.verbose:
                    print("Error while listening to messages: %s", e)

                # Attempt to reconnect if connection drops
                self.logger.info("Attempting to reconnect...")
                if self.verbose:
                    print("Attempting to reconnect...")
                await asyncio.sleep(3)  # backoff
                await self._connect()

    async def close(self):
        """Close the WebSocket connection."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        if self._ws is not None:  # and not self._ws.closed:
            await self._ws.close()
            self.logger.info("WebSocket connection closed.")
            if self.verbose:
                print("WebSocket connection closed.")

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()


class WebSocket(BaseWebSocket):
    """
    Synchronous WebSocket client for streaming real time pricing data.
    """

    def __init__(self, url: str = "wss://streamer.finance.yahoo.com/?version=2", verbose=True):
        """
        Initialize the WebSocket client.

        Args:
            url (str): The WebSocket server URL. Defaults to Yahoo Finance's WebSocket URL.
            verbose (bool): Flag to enable or disable print statements. Defaults to True.
        """
        super().__init__(url, verbose)

    def _connect(self):
        try:
            if self._ws is None:
                self._ws = sync_connect(self.url)
                self.logger.info("Connected to WebSocket.")
                if self.verbose:
                    print("Connected to WebSocket.")
        except Exception as e:
            self.logger.error("Failed to connect to WebSocket: %s", e, exc_info=True)
            if self.verbose:
                print(f"Failed to connect to WebSocket: {e}")
            self._ws = None
            raise

    def subscribe(self, symbols: Union[str, List[str]]):
        """
        Subscribe to a stock symbol or a list of stock symbols.

        Args:
            symbols (Union[str, List[str]]): Stock symbol(s) to subscribe to.
        """
        self._connect()

        if isinstance(symbols, str):
            symbols = [symbols]

        self._subscriptions.update(symbols)

        message = {"subscribe": list(self._subscriptions)}
        self._ws.send(json.dumps(message))

        self.logger.info(f"Subscribed to symbols: {symbols}")
        if self.verbose:
            print(f"Subscribed to symbols: {symbols}")

    def unsubscribe(self, symbols: Union[str, List[str]]):
        """
        Unsubscribe from a stock symbol or a list of stock symbols.

        Args:
            symbols (Union[str, List[str]]): Stock symbol(s) to unsubscribe from.
        """
        self._connect()

        if isinstance(symbols, str):
            symbols = [symbols]

        self._subscriptions.difference_update(symbols)

        message = {"unsubscribe": symbols}
        self._ws.send(json.dumps(message))

        self.logger.info(f"Unsubscribed from symbols: {symbols}")
        if self.verbose:
            print(f"Unsubscribed from symbols: {symbols}")

    def listen(self, message_handler: Optional[Callable[[dict], None]] = None):
        """
        Start listening to messages from the WebSocket server.

        Args:
            message_handler (Optional[Callable[[dict], None]]): Optional function to handle received messages.
        """
        self._connect()

        self.logger.info("Listening for messages...")
        if self.verbose:
            print("Listening for messages...")

        while True:
            try:
                message = self._ws.recv()
                message_json = json.loads(message)
                encoded_data = message_json.get("message", "")
                decoded_message = self._decode_message(encoded_data)

                if message_handler:
                    try:
                        message_handler(decoded_message)
                    except Exception as handler_exception:
                        self.logger.error("Error in message handler: %s", handler_exception, exc_info=True)
                        if self.verbose:
                            print("Error in message handler:", handler_exception)
                else:
                    print(decoded_message)

            except KeyboardInterrupt:
                if self.verbose:
                    print("Received keyboard interrupt.")
                self.close()
                break

            except Exception as e:
                self.logger.error("Error while listening to messages: %s", e, exc_info=True)
                if self.verbose:
                    print("Error while listening to messages: %s", e)
                break

    def close(self):
        """Close the WebSocket connection."""
        if self._ws is not None:
            self._ws.close()
            self.logger.info("WebSocket connection closed.")
            if self.verbose:
                print("WebSocket connection closed.")

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
