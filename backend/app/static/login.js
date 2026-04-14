const elements = {
    googleSigninButton: document.getElementById("google-signin-button"),
    loginStatus: document.getElementById("login-status"),
};

initLoginPage();

async function initLoginPage() {
    try {
        const response = await fetch("/auth/config");
        const payload = await parseJson(response);
        if (!response.ok) {
            throw new Error(payload.detail || "Unable to load login configuration.");
        }

        if (!payload.is_configured || !payload.client_id) {
            throw new Error("Login is not configured on this server.");
        }

        await waitForGoogleIdentity();
        window.google.accounts.id.initialize({
            client_id: payload.client_id,
            callback: handleCredentialResponse,
            auto_select: false,
            cancel_on_tap_outside: true,
            context: "signin",
        });
        window.google.accounts.id.renderButton(
            elements.googleSigninButton,
            {
                theme: "outline",
                size: "large",
                text: "signin_with",
                shape: "pill",
                width: 180,
            },
        );
        showStatus("neutral", "Use your Twinkl account to log in.");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Login could not be initialized.";
        showStatus("error", message);
    }
}

async function handleCredentialResponse(response) {
    const credential = typeof response?.credential === "string" ? response.credential : "";
    if (!credential) {
        showStatus("error", "Login did not return a valid credential.");
        return;
    }

    showStatus("neutral", "Verifying your account...");

    try {
        const authResponse = await fetch("/auth/google", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ credential }),
        });
        const payload = await parseJson(authResponse);
        if (!authResponse.ok) {
            throw new Error(payload.detail || "Login failed.");
        }
        window.location.assign("/");
    } catch (error) {
        const message = error instanceof Error ? error.message : "Login failed.";
        showStatus("error", message);
    }
}

function waitForGoogleIdentity() {
    return new Promise((resolve, reject) => {
        let attempts = 0;
        const maxAttempts = 60;
        const interval = window.setInterval(() => {
            attempts += 1;
            if (window.google?.accounts?.id) {
                window.clearInterval(interval);
                resolve();
                return;
            }
            if (attempts >= maxAttempts) {
                window.clearInterval(interval);
                reject(new Error("Login script did not load."));
            }
        }, 200);
    });
}

function showStatus(kind, message) {
    elements.loginStatus.textContent = message;
    elements.loginStatus.className = `status-message status-${kind}`;
}

async function parseJson(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}
