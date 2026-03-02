function login() {

    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    fetch("http://127.0.0.1:8000/api/token/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        })
        .then(res => res.json())
        .then(data => {

            if (data.access) {

                localStorage.setItem("access_token", data.access);
                localStorage.setItem("refresh_token", data.refresh);

                window.location.href = "/dashboard/";

            } else {
                document.getElementById("error").innerText = "Invalid credentials";
            }

        })
        .catch(error => {
            document.getElementById("error").innerText = "Server error";
        });
}