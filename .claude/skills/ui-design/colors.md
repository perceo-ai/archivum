# Color System Reference

Complete color palette, semantic usage, dark mode mappings, and accessibility guidelines.

---

## The 60-30-10 Rule

- **60%** Neutral/Background colors (establishes calm)
- **30%** Secondary colors (supporting content)
- **10%** Accent colors (calls to action, emphasis)

---

## Primary Color: Custom (#0891B2)

Trustworthy, professional. Used for primary actions, navigation, and key UI elements.

```
custom-50:   #ECFEFF  Very light background
custom-100:  #CFFAFE  Light background, active nav items
custom-200:  #A5F3FC  Light border
custom-300:  #67E8F9  Medium highlight
custom-400:  #22D3EE  Medium
custom-500:  #06B6D4  Light primary
custom-600:  #0891B2  PRIMARY (default)
custom-700:  #0E7490  Dark primary (hover)
custom-800:  #155E75  Very dark (active)
custom-900:  #164E63  Darkest (text on light bg)
```

### Usage

```jsx
// Primary button
<button className="bg-custom-600 text-white hover:bg-custom-700">Action</button>

// Primary link
<a className="text-custom-600 hover:text-custom-700">Link</a>

// Highlight background
<div className="bg-custom-50 border border-custom-200 text-custom-900">Highlighted</div>

// Active nav item
<a className="bg-custom-100 text-custom-600">Active</a>
```

---

## Secondary Colors: Grays (60% of palette)

For text, backgrounds, borders, and secondary information.

```
gray-50:   #F9FAFB  Backgrounds, light sections
gray-100:  #F3F4F6  Hover states, disabled buttons
gray-200:  #E5E7EB  Borders, dividers
gray-300:  #D1D5DB  Stronger borders
gray-400:  #9CA3AF  Placeholder text
gray-500:  #6B7280  Tertiary text
gray-600:  #4B5563  Secondary text (body)
gray-700:  #374151  Body text emphasis
gray-800:  #1F2937  Headlines
gray-900:  #111827  Primary text
gray-950:  #030712  Dark mode background
```

### Text Hierarchy

```jsx
<p className="text-gray-900">Primary text (highest contrast)</p>
<p className="text-gray-700">Body text (emphasis)</p>
<p className="text-gray-600">Secondary text (default body)</p>
<p className="text-gray-500">Tertiary text (minimal emphasis)</p>
<p className="text-gray-400">Muted / placeholder text</p>
```

### Background Hierarchy

```jsx
<div className="bg-white">Main content area</div>
<div className="bg-gray-50">Secondary background, card hover</div>
<div className="bg-gray-100">Disabled state, light section background</div>
```

### Border Hierarchy

```jsx
<div className="border border-gray-200">Default border (subtle)</div>
<div className="border border-gray-300">Stronger border (emphasis)</div>
```

---

## Accent Color: Custom (#EC4899)

Warm accent for highlights and secondary CTAs.

```
custom-50:   #FDF2F8
custom-100:  #FCE7F3
custom-200:  #FBCFE8
custom-400:  #F472B6
custom-500:  #EC4899  PRIMARY ACCENT
custom-600:  #DB2777  Dark accent (hover)
custom-700:  #BE185D
custom-800:  #9D174D
```

### Usage

```jsx
// Accent CTA
<button className="bg-custom-500 text-white hover:bg-custom-600">Highlight Action</button>

// Highlight badge
<span className="px-2 py-1 bg-custom-100 text-custom-800 rounded-full text-xs font-medium">
  Featured
</span>

// Accent background
<div className="bg-custom-50 border border-custom-200 text-custom-900">Featured section</div>
```

---

## Semantic Status Colors

### Success: Emerald

```jsx
// Alert
<div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
  <p className="text-emerald-800">Action completed successfully</p>
</div>

// Badge
<span className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded text-xs font-medium">
  Active
</span>
```

### Warning: Amber

```jsx
// Alert
<div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
  <p className="text-amber-800">Attention required</p>
</div>

// Badge
<span className="px-2 py-1 bg-amber-100 text-amber-700 rounded text-xs font-medium">
  Pending
</span>
```

### Error / Destructive: Rose

```jsx
// Alert
<div className="bg-rose-50 border border-rose-200 rounded-lg p-4">
  <p className="text-rose-800">Something went wrong</p>
</div>

// Destructive button
<button className="bg-rose-600 text-white hover:bg-rose-700">Delete</button>

// Rose scale
rose-50:   #FFF5F7
rose-100:  #FFE4E8
rose-200:  #FECDD3
rose-500:  #F43F5E  Primary destructive
rose-600:  #E11D48  Dark destructive (hover)
```

### Info: Blue

```jsx
<div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
  <p className="text-blue-800">New report available</p>
</div>
```

### Premium / AI: Purple Gradient

```jsx
<div className="bg-gradient-to-r from-custom-500 to-fuchsia-500 text-white p-4 rounded-lg">
  <p className="font-semibold">AI-Powered Feature (Premium)</p>
</div>
```

---

## Color Implementation Object

Reusable semantic color mappings:

```jsx
export const colors = {
  bg: {
    primary: 'bg-white',
    secondary: 'bg-gray-50',
    tertiary: 'bg-gray-100',
    overlay: 'bg-black/50',
  },
  text: {
    primary: 'text-gray-900',
    secondary: 'text-gray-600',
    tertiary: 'text-gray-500',
    muted: 'text-gray-400',
  },
  button: {
    primary: 'bg-custom-600 text-white hover:bg-custom-700',
    secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200',
    ghost: 'text-custom-600 hover:bg-custom-50',
  },
  status: {
    success: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    warning: 'text-amber-700 bg-amber-50 border-amber-200',
    error: 'text-rose-700 bg-rose-50 border-rose-200',
    info: 'text-blue-700 bg-blue-50 border-blue-200',
  },
}
```

---

## Dark Mode Color Palette

### Backgrounds

Never use pure black (`#000000`). Use gray-950 for warmth.

```jsx
<div className="bg-white dark:bg-gray-950">Primary background</div>
<div className="bg-gray-50 dark:bg-gray-900">Secondary background</div>
<div className="bg-gray-100 dark:bg-gray-800">Tertiary background</div>
```

### Text

```jsx
<p className="text-gray-900 dark:text-white">Primary text</p>
<p className="text-gray-600 dark:text-gray-300">Secondary text</p>
<p className="text-gray-500 dark:text-gray-400">Tertiary text</p>
<p className="text-gray-400 dark:text-gray-600">Muted text</p>
```

### Borders

```jsx
<div className="border border-gray-200 dark:border-gray-700">Default border</div>
<div className="border border-gray-300 dark:border-gray-600">Strong border</div>
```

### Interactive Colors

Slightly lighter primary in dark mode for eye comfort:

```jsx
<button className="bg-custom-600 dark:bg-custom-500 text-white
  hover:bg-custom-700 dark:hover:bg-custom-600">
  Submit
</button>
```

### Status Colors in Dark Mode

Use `-950` backgrounds and `-200` text on dark:

```jsx
<div className="bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800">
  <p className="text-emerald-800 dark:text-emerald-200">Success</p>
</div>

<div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800">
  <p className="text-amber-800 dark:text-amber-200">Warning</p>
</div>

<div className="bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800">
  <p className="text-rose-800 dark:text-rose-200">Error</p>
</div>
```

### Shadows in Dark Mode

Increase shadow depth (dark backgrounds need stronger shadows):

```jsx
<div className="shadow-sm dark:shadow-md hover:shadow-md dark:hover:shadow-lg transition-shadow">
  Card
</div>
```

### Complete Dark Mode Card

```jsx
<div className="p-6 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700
  rounded-lg shadow-sm dark:shadow-lg hover:shadow-md dark:hover:shadow-xl transition-shadow">

  <div className="flex items-center justify-between mb-4">
    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Title</h3>
    <span className="px-2 py-1 bg-custom-100 dark:bg-custom-900/30
      text-custom-700 dark:text-custom-300 rounded text-xs font-medium">
      Badge
    </span>
  </div>

  <div className="space-y-3 mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
    <div className="flex justify-between">
      <span className="text-sm text-gray-600 dark:text-gray-400">Label</span>
      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">Value</span>
    </div>
  </div>

  <div className="flex gap-2">
    <button className="flex-1 px-4 py-2 bg-custom-600 dark:bg-custom-500 text-white
      font-medium rounded-sm hover:bg-custom-700 dark:hover:bg-custom-600 transition-colors">
      Primary
    </button>
    <button className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600
      text-gray-700 dark:text-gray-300 font-medium rounded-sm
      hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
      Secondary
    </button>
  </div>
</div>
```

### Dark Mode Setup

```jsx
// tailwind.config.js
module.exports = {
  darkMode: 'class',
}

// Toggle implementation
export function DarkModeProvider({ children }) {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('theme')
    if (saved) {
      setIsDark(saved === 'dark')
    } else {
      setIsDark(window.matchMedia('(prefers-color-scheme: dark)').matches)
    }
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', isDark)
    localStorage.setItem('theme', isDark ? 'dark' : 'light')
  }, [isDark])

  return (
    <div>
      <button onClick={() => setIsDark(!isDark)}>
        {isDark ? 'Light Mode' : 'Dark Mode'}
      </button>
      {children}
    </div>
  )
}
```

---

## Contrast & Accessibility

WCAG AA compliance:
- **Normal text** (14px+): 4.5:1 contrast ratio
- **Large text** (18px+ or 14px bold): 3:1 contrast ratio

```jsx
// Good contrast
<p className="text-gray-700 bg-white">Content</p>   // 8.2:1 ratio

// Poor contrast (fails accessibility)
<p className="text-gray-400 bg-white">Content</p>    // 2.0:1 ratio

// White on indigo
<div className="bg-custom-600 text-white">Content</div>  // 9.5:1 ratio
```

### Rules

- Body text on white: use `text-gray-600` or darker
- Labels: use `text-gray-700` with `font-medium`
- Placeholder text (`text-gray-400`) is acceptable since it disappears on input
- Always test contrast when using colored backgrounds
