# Анимация расписания (`schedule-animation`)

Фронт читает **те же сущности, что и пайплайн crocs**, из статики Vite — каталог **`public/`** (URL вида `/schedule.xlsx` от корня приложения).

## Откуда брать файлы (чтобы данные совпадали с прогоном crocs)

После успешного `python -m crocs` (или эквивалента) скопируйте из **`artifacts/`** в **`schedule-animation/public/`**:

| Файл в `public/` | Источник в репозитории | Назначение |
|------------------|------------------------|------------|
| **`schedule.xlsx`** | `artifacts/schedule.xlsx` | Смены: `ds`, `station_key`, `employee_id`, `starttime`, `finishtime` |
| **`forecast.xlsx`** | `artifacts/forecast.xlsx` | Гости по часу: `sale_date`, `sale_hour`, `guests_count` |
| **`staffing_requirements.xlsx`** | свой норматив / экспорт (если используете) | Нормы и опционально посетители по слоту |

**PowerShell** (из корня репозитория `crocs`):

```powershell
Copy-Item -Force artifacts\forecast.xlsx schedule-animation\public\forecast.xlsx
Copy-Item -Force artifacts\schedule.xlsx schedule-animation\public\schedule.xlsx
```

Без **`forecast.xlsx`** в `public/` число гостей в шапке может заполняться из колонок staffing или стабильным запасным значением по слоту.

При **`npm run dev`** запросы **`/api/...`** проксируются на бэкенд crocs (`vite.config.ts`, по умолчанию `http://127.0.0.1:8000`). Для режима «только статика» достаточно файлов в `public/`.

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
