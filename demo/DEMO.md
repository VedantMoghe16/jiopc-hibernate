# Demo: Cross-VM Session Restore

In this demo, I tested the `jiopc-hibernate` session restore feature.

I opened 3 to 4 applications, including a browser, terminal, file manager, and document/file window. After opening these apps, I logged out of the LxQt session. During logout, `jiopc-hibernate` saved the running session into the user's home directory.

After that, I logged back in again. The restore service detected the saved session and restored the previously opened applications. The browser and other apps reopened successfully, showing that the session was saved and restored correctly.

This demonstrates that the project can preserve a user's working session across logout and login. In a cross-VM setup with the same home directory mounted, the same saved session can also be restored on another VM.

Thank you.
