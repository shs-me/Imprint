"""Base synchronous & asynchronous REST client."""

from abc import ABC
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, Self, TypeVar, final, overload

import httpx
import msgspec

from imprint._core.types import LoggerProtocol, SetLogMethodSignature

# Generic type for msgspec decoding target
T = TypeVar("T")


class RestError(Exception):
    """Base exception class for all REST client errors."""


class RestConnectionError(RestError):
    """Raised when connection establishment or network requests fail."""


class RestTimeoutError(RestError):
    """Raised when HTTP operations exceed configured timeout limits."""


class RestResponseError(RestError):
    """Raised on HTTP error status codes (4xx, 5xx).

    Parameters
    ----------
    status_code : int
        HTTP response status code returned by the server.
    message : str
        Human-readable error explanation.
    response_body : bytes
        Raw raw byte content returned in the error response body.
    headers : httpx.Headers
        Response headers associated with the error.

    Attributes
    ----------
    status_code : int
        HTTP response status code returned by the server.
    response_body : bytes
        Raw byte content returned in the error response body.
    headers : httpx.Headers
        Response headers associated with the error.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        response_body: bytes,
        headers: httpx.Headers,
    ) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code: int = status_code
        self.response_body: bytes = response_body
        self.headers: httpx.Headers = headers


class RestDecodeError(RestError):
    """Raised when response body deserialization via msgspec fails."""


@dataclass(slots=True)
class BaseREST(ABC):
    """Base synchronous and asynchronous REST client utilizing httpx and msgspec.

    Parameters
    ----------
    logger : LoggerProtocol | SetLogMethodSignature
        Configured logger instance or logging callback function.

    Attributes
    ----------
    logger : LoggerProtocol | SetLogMethodSignature
        Configured logger instance or logging callback function.
    base_url : str
        Base URL endpoint for all outbound requests. Must be defined by subclasses.
    headers : dict[str, str]
        Default HTTP headers included in every request.
    connect_timeout : float | None, default=10.0
        Maximum duration in seconds to wait for socket connection establishment.
    read_timeout : float | None, default=10.0
        Maximum duration in seconds to wait for socket read operations.
    write_timeout : float | None, default=10.0
        Maximum duration in seconds to wait for socket write operations.
    pool_timeout : float | None, default=10.0
        Maximum duration in seconds to wait for an available connection from the pool.
    """

    logger: LoggerProtocol | SetLogMethodSignature

    base_url: str = field(init=False)
    headers: dict[str, str] = field(
        default_factory=lambda: {"User-Agent": "Imprint/0.1.0"}, init=False
    )
    connect_timeout: float | None = field(default=10.0, init=False)
    read_timeout: float | None = field(default=10.0, init=False)
    write_timeout: float | None = field(default=10.0, init=False)
    pool_timeout: float | None = field(default=10.0, init=False)

    __timeout: httpx.Timeout | None = field(default=None, init=False)
    __sync_client: httpx.Client | None = field(
        default=None, init=False, repr=False
    )
    __async_client: httpx.AsyncClient | None = field(
        default=None, init=False, repr=False
    )
    __encoder: msgspec.json.Encoder = field(
        default_factory=msgspec.json.Encoder, init=False, repr=False
    )
    __units: list[str] = field(
        default_factory=lambda: ["B", "KB", "MB", "GB", "TB"], init=False
    )

    @final
    def log(
        self, msg: str, level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    ) -> None:
        """Emit a log message via the configured logger or callback function.

        Parameters
        ----------
        msg : str
            Log message content to record.
        level : {'INFO', 'WARNING', 'ERROR'}, default='INFO'
            Severity level of the log record.
        """
        if callable(self.logger):
            self.logger(f"{level} | {msg}")
        else:
            if level == "INFO":
                self.logger.info(msg)
            elif level == "WARNING":
                self.logger.warning(msg)
            else:
                self.logger.error(msg)

    @final
    def format_bytes(self, size: float) -> str:
        """Format a raw byte size into a human-readable string with appropriate units.

        Parameters
        ----------
        size : float
            Raw size value in bytes. Must be non-negative.

        Returns
        -------
        str
            Formatted string representation with appropriate unit suffix (B, KB, MB, GB, TB).
        """
        i: int = 0
        while size >= 1024 and i < (len(self.__units) - 1):
            size, i = size / 1024, i + 1

        return f"{size:.2f} {self.__units[i]}"

    @final
    @property
    def _timeout(self) -> httpx.Timeout:
        """Retrieve or update the consolidated httpx.Timeout instance."""
        if self.__timeout is None:
            self.__timeout = httpx.Timeout(
                connect=self.connect_timeout,
                read=self.read_timeout,
                write=self.write_timeout,
                pool=self.pool_timeout,
            )
        else:
            if self.__timeout.connect != self.connect_timeout:
                self.__timeout.connect = self.connect_timeout

            if self.__timeout.read != self.read_timeout:
                self.__timeout.read = self.read_timeout

            if self.__timeout.write != self.write_timeout:
                self.__timeout.write = self.write_timeout

            if self.__timeout.pool != self.pool_timeout:
                self.__timeout.pool = self.pool_timeout

        return self.__timeout

    @final
    @property
    def _sync_client(self) -> httpx.Client:
        """Retrieve the lazy-initialized synchronous httpx.Client instance.

        Avoids cross-process socket leaks by instantiating or validating client state on demand.
        """

        if self.__sync_client is None or self.__sync_client.is_closed:
            self.__sync_client = httpx.Client(
                base_url=self.base_url,
                timeout=self._timeout,
                headers=self.headers,
                follow_redirects=True,
                http2=False,
            )
        return self.__sync_client

    @final
    @property
    def _async_client(self) -> httpx.AsyncClient:
        """Retrieve the lazy-initialized asynchronous httpx.AsyncClient instance.

        Bound to the calling event loop to prevent event loop cross-contamination.
        """

        if self.__async_client is None or self.__async_client.is_closed:
            self.__async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                headers=self.headers,
                follow_redirects=True,
                http2=False,
            )
        return self.__async_client

    @final
    def close_sync(self) -> None:
        """Close active synchronous client session and release network resources."""

        if self.__sync_client is not None and not self._sync_client.is_closed:
            self._sync_client.close()
            self.__sync_client = None

    @final
    async def close_async(self) -> None:
        """Close active asynchronous client session and release network resources."""

        if self.__async_client is not None and not self._async_client.is_closed:
            await self._async_client.aclose()
            self.__async_client = None

    # - Context manager support -
    @final
    def __enter__(self) -> Self:
        """Enter the synchronous context manager.

        Returns
        -------
        Self
            The REST client instance.
        """
        return self

    @final
    def __exit__(self, *args: object) -> None:
        """Exit the synchronous context manager and close client sessions."""
        self.close_sync()

    @final
    async def __aenter__(self) -> Self:
        """Enter the asynchronous context manager.

        Returns
        -------
        Self
            The REST client instance.
        """
        return self

    @final
    async def __aexit__(self, *args: object) -> None:
        """Exit the asynchronous context manager and close client sessions."""
        await self.close_async()

    # - - -

    @final
    def _prepare_payload(
        self,
        json_body: Any | None,
        content: bytes | None,
        headers: dict[str, str] | None,
    ) -> tuple[bytes | None, dict[str, str] | None]:
        """Prepare request body payload and merge custom headers.

        Parameters
        ----------
        json_body : Any | None
            JSON-serializable payload object, string, or bytes.
        content : bytes | None
            Raw binary payload bytes.
        headers : dict[str, str] | None
            Request-specific header overrides.

        Returns
        -------
        tuple[bytes | None, dict[str, str] | None]
            Encoded request payload bytes and merged header dictionary.
        """
        merged_headers: dict[str, str] = {**self.headers, **(headers or {})}

        if json_body is not None:
            if isinstance(json_body, (str, bytes)):
                encoded_bytes = (
                    json_body.encode("utf-8")
                    if isinstance(json_body, str)
                    else json_body
                )
            else:
                encoded_bytes = self.__encoder.encode(json_body)

            merged_headers["Content-Type"] = "application/json"
            return encoded_bytes, merged_headers

        return content, merged_headers

    @overload
    def _decode_response(
        self, raw_content: bytes, response_type: type[T]
    ) -> T: ...
    @overload
    def _decode_response(
        self, raw_content: bytes, response_type: None
    ) -> Any: ...
    @final
    def _decode_response(
        self, raw_content: bytes, response_type: type[T] | None
    ):
        """Decode response bytes using msgspec with optional schema enforcement.

        Parameters
        ----------
        raw_content : bytes
            Raw response body bytes received from the server.
        response_type : type[T] | None
            Target msgspec decodable type structure. If None, decodes into generic Python primitives.

        Returns
        -------
        T | Any
            Decoded Python object or primitive matching the target response type.

        Raises
        ------
        RestDecodeError
            If msgspec encounters a decoding or validation failure.
        """

        if response_type is bytes:
            return raw_content

        try:
            if response_type is not None:
                return msgspec.json.decode(raw_content, type=response_type)

            return msgspec.json.decode(raw_content)

        except (msgspec.DecodeError, msgspec.ValidationError) as exc:
            self.log(
                f"Failed to decode response with msgspec: {exc} | Raw body: {raw_content[:200]!r}",
                level="ERROR",
            )
            raise RestDecodeError(f"msgspec decode error: {exc}") from exc

    @final
    @contextmanager
    def _handle_httpx_errors(
        self, method: str, endpoint: str, is_async: bool = False
    ) -> Generator[None]:
        """Translate httpx exceptions into RestError subtypes within a context manager.

        Parameters
        ----------
        method : str
            HTTP request method (e.g., 'GET', 'POST').
        endpoint : str
            Target URL path or endpoint.
        is_async : bool, default=False
            Flag indicating whether the operation is asynchronous.

        Yields
        ------
        None
            Yields control to the guarded request execution block.

        Raises
        ------
        RestTimeoutError
            If the HTTP request exceeds configured timeout limits.
        RestConnectionError
            If socket connection fails or request errors occur.
        RestResponseError
            If the server returns an HTTP error status code (4xx, 5xx).
        """

        mode: str = "Async" if is_async else "Sync"
        method_upper: str = method.upper()

        try:
            yield
        except httpx.TimeoutException as exc:
            msg: str = f"{mode} Timeout [{method_upper} {endpoint}]: {exc}"
            self.log(msg, level="WARNING")
            raise RestTimeoutError(msg) from exc

        except httpx.ConnectError as exc:
            msg = f"{mode} Connection Failed [{method_upper} {endpoint}]: {exc}"
            self.log(msg, level="ERROR")
            raise RestConnectionError(msg) from exc

        except httpx.HTTPStatusError as exc:
            msg = f"HTTP Error [{exc.response.status_code} on {method_upper} {endpoint}]"
            self.log(
                f"{msg} | Body: {exc.response.content[:300]!r}", level="ERROR"
            )
            raise RestResponseError(
                status_code=exc.response.status_code,
                message=str(exc),
                response_body=exc.response.content,
                headers=exc.response.headers,
            ) from exc

        except httpx.RequestError as exc:
            msg = f"{mode} Request Error [{method_upper} {endpoint}]: {exc}"
            self.log(msg, level="ERROR")
            raise RestConnectionError(msg) from exc

    @overload
    def send_sync(
        self,
        method: str,
        endpoint: str,
        response_type: type[T],
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> T: ...
    @overload
    def send_sync(
        self,
        method: str,
        endpoint: str,
        response_type: None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any: ...
    @final
    def send_sync(
        self,
        method: str,
        endpoint: str,
        response_type: type[T] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        """Execute a synchronous HTTP request and return the decoded msgspec object.

        Parameters
        ----------
        method : str
            HTTP request verb (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        endpoint : str
            Relative or absolute target URL endpoint.
        response_type : type[T] | None, default=None
            Target msgspec decoding schema class. If None, returns raw decoded JSON primitives.
        params : dict[str, Any] | None, default=None
            Query parameters to append to the request URL.
        json_body : Any | None, default=None
            Payload object to serialize as JSON.
        content : bytes | None, default=None
            Raw binary request body bytes.
        headers : dict[str, str] | None, default=None
            Additional request-specific header overrides.
        timeout : float | None, default=None
            Per-request timeout override in seconds.

        Returns
        -------
        T | Any
            Decoded response parsed into ``response_type`` or generic Python data structures.

        Raises
        ------
        RestTimeoutError
            If the request exceeds timeout limits.
        RestConnectionError
            If connection establishment or request transport fails.
        RestResponseError
            If the server returns a 4xx or 5xx status code.
        RestDecodeError
            If response deserialization fails.
        """

        payload, req_headers = self._prepare_payload(
            json_body, content, headers
        )
        client: httpx.Client = self._sync_client

        with self._handle_httpx_errors(method, endpoint, is_async=False):
            response: httpx.Response = client.request(
                method=method.upper(),
                url=endpoint,
                params=params,
                content=payload,
                headers=req_headers,
                timeout=timeout or self._timeout,
            )
            response.raise_for_status()

        return self._decode_response(response.content, response_type)

    @overload
    async def send_async(
        self,
        method: str,
        endpoint: str,
        response_type: type[T],
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> T: ...
    @overload
    async def send_async(
        self,
        method: str,
        endpoint: str,
        response_type: None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any: ...
    @final
    async def send_async(
        self,
        method: str,
        endpoint: str,
        response_type: type[T] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        """Execute an asynchronous HTTP request and return the decoded msgspec object.

        Parameters
        ----------
        method : str
            HTTP request verb (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        endpoint : str
            Relative or absolute target URL endpoint.
        response_type : type[T] | None, default=None
            Target msgspec decoding schema class. If None, returns raw decoded JSON primitives.
        params : dict[str, Any] | None, default=None
            Query parameters to append to the request URL.
        json_body : Any | None, default=None
            Payload object to serialize as JSON.
        content : bytes | None, default=None
            Raw binary request body bytes.
        headers : dict[str, str] | None, default=None
            Additional request-specific header overrides.
        timeout : float | None, default=None
            Per-request timeout override in seconds.

        Returns
        -------
        T | Any
            Decoded response parsed into ``response_type`` or generic Python data structures.

        Raises
        ------
        RestTimeoutError
            If the request exceeds timeout limits.
        RestConnectionError
            If connection establishment or request transport fails.
        RestResponseError
            If the server returns a 4xx or 5xx status code.
        RestDecodeError
            If response deserialization fails.
        """

        payload, req_headers = self._prepare_payload(
            json_body,
            content,
            headers,
        )
        client: httpx.AsyncClient = self._async_client

        with self._handle_httpx_errors(method, endpoint, is_async=True):
            response: httpx.Response = await client.request(
                method=method.upper(),
                url=endpoint,
                params=params,
                content=payload,
                headers=req_headers,
                timeout=timeout or self._timeout,
            )
            response.raise_for_status()

        return self._decode_response(response.content, response_type)
