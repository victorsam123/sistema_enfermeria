"""Amplía solo las cargas de guardias; conserva los límites de los demás módulos."""


def configure_guardia_request(state):
    base = state.app.request_class

    class GuardiaRequest(base):
        @property
        def max_content_length(self):
            if self.blueprint == 'guardias' and self.method == 'POST':
                return 2 * 1024 * 1024
            return super().max_content_length

    state.app.request_class = GuardiaRequest
