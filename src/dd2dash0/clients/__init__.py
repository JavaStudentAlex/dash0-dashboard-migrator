"""HTTP clients for the Datadog source API and the Dash0 target API."""

import httpx


class APIError(RuntimeError):
    """A remote API answered with a non-2xx status.

    The message holds the method, URL, status and response body. Credentials
    travel only in request headers, so they never appear in the message.
    """


def checked_json(response: httpx.Response) -> dict:
    """Return the decoded JSON body of a successful response.

    :param response: The HTTP response to check.
    :returns: The decoded JSON body.
    :raises APIError: If the status is not 2xx.
    """
    if not response.is_success:
        request = response.request
        raise APIError(f"{request.method} {request.url} -> HTTP {response.status_code}: {response.text}")
    return response.json()
