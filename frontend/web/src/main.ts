import { createApp } from "vue"
import App from "./App.vue"
import router from "./router/index.ts"
import "./style.css"
import "./styles/design-tokens.css"

createApp(App).use(router).mount("#app")
