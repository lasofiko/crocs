# Анимация расписания (`schedule-animation`)

В режиме **`npm run dev`** и **`vite preview`** фронт **сначала** берёт таблицы из **`artifacts/`** в корне репозитория `crocs` (те же пути, что после пайплайна):

- **`artifacts/schedule.xlsx`**
- **`artifacts/staffing_requirements.xlsx`**
- **`artifacts/forecast.xlsx`** (если есть — для гостей по часам)

Vite отдаёт их по URL **`/crocs-artifacts/<имя файла>`** (см. `vite.config.ts`). Если файла в `artifacts/` нет, используется запасной вариант — **`schedule-animation/public/`** с тем же именем.

## Когда нужен `public/`

- **Статический хост** без Vite (например, только `dist/` на nginx): туда по-прежнему нужно положить копии xlsx **или** настроить прокси на `/crocs-artifacts/` → каталог `artifacts` на сервере.
- Локально после **`npm run build`** без копирования в `public/` убедитесь, что **`vite preview`** используется с тем же конфигом (артефакты подхватятся).

## Копирование в `public/` (опционально)

Если нужен демо без файлов в `artifacts/`, можно скопировать из пайплайна в **`schedule-animation/public/`**:

| Файл в `public/` | Типичный источник |
|------------------|-------------------|
| **`schedule.xlsx`** | `artifacts/schedule.xlsx` |
| **`forecast.xlsx`** | `artifacts/forecast.xlsx` |
| **`staffing_requirements.xlsx`** | свой норматив / `artifacts/…` |

**PowerShell** (из корня `crocs`):

```powershell
Copy-Item -Force artifacts\forecast.xlsx schedule-animation\public\forecast.xlsx
Copy-Item -Force artifacts\schedule.xlsx schedule-animation\public\schedule.xlsx
```

При **`npm run dev`** запросы **`/api/...`** проксируются на бэкенд crocs (`vite.config.ts`, по умолчанию `http://127.0.0.1:8000`).

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
