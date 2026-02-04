# 🚀 Quick Start Guide

## Prerequisites

- Node.js 18+ and npm
- Backend API running on `http://localhost:8000`

## Installation

```bash
cd web
npm install
```

## Development

```bash
npm run dev
```

Visit `http://localhost:3000`

## Usage Flow

### 1. Create a Project
- Click "Create New Project"
- Fill in:
  - **Name**: Your project name
  - **Description**: Brief description
  - **Script Content**: Paste your novel/script (min 50 chars)
  - **Style Preset**: Choose animation style
- Click "Create Project"

### 2. Build Assets
- On project detail page, click "Build Assets"
- System extracts characters from script
- Generates reference images via AI
- Status changes to "ASSETS_READY"

### 3. Generate Storyboard
- Click "Generate Storyboard"
- LLM analyzes script and creates shots
- View shots in "Storyboard" tab
- Status changes to "STORYBOARD_READY"

### 4. Start Production Pipeline
- Click "Start Production Pipeline"
- System renders all shots in parallel
- Monitor progress in "Renders" tab
- Status changes through: RENDERING → COMPOSITED → DONE

### 5. View Output
- When done, "Output" tab appears
- Watch final video

## Features

### Project List Page
- Grid of all projects
- Status badges
- Click card to view details
- Pagination for large lists

### Project Detail Page
- **Overview**: Script and metadata
- **Characters**: Character cards with images
- **Storyboard**: Shot timeline with descriptions
- **Renders**: Job progress with real-time updates
- **Output**: Video player (when complete)

### Real-time Updates
- Auto-polls every 3 seconds during rendering
- Progress bars show completion percentage
- Status badges update automatically

### Error Handling
- Toast notifications for all errors
- User-friendly error messages
- Retry failed operations

## Keyboard Shortcuts

- `Esc`: Close modals
- `Enter`: Submit forms (when focused)

## Tips

1. **Script Format**: Use clear scene descriptions and dialogue
2. **Style Presets**: Choose style that matches your content
3. **Parallel Renders**: Default is 4, increase for faster rendering (if resources allow)
4. **Monitoring**: Keep browser tab open during rendering for real-time updates

## Troubleshooting

### API Connection Failed
- Ensure backend is running on port 8000
- Check `vite.config.ts` proxy settings

### Images Not Loading
- Check backend `output/` directory permissions
- Verify image paths in database

### Slow Rendering
- Reduce parallel renders
- Check backend logs for provider issues

## Development

### Project Structure
```
src/
├── api/          # API client
├── components/   # Reusable components
├── composables/  # Reusable logic
├── stores/       # Pinia stores
├── types/        # TypeScript types
└── views/        # Page components
```

### Adding New Features

1. **New API Endpoint**:
   - Add type to `types/api.ts`
   - Add method to `api/client.ts`

2. **New Component**:
   - Create in `components/`
   - Use `<script setup>` syntax
   - Import types from `@/types/api`

3. **New Page**:
   - Create in `views/`
   - Add route to `main.ts`

### Code Style

- Use Composition API with `<script setup>`
- Strict TypeScript (no `any`)
- Tailwind for styling
- Naive UI for components
- Self-documenting code (minimal comments)

## Build for Production

```bash
npm run build
```

Output in `dist/` directory.

## Support

For issues or questions:
1. Check backend logs
2. Check browser console
3. Review `IMPLEMENTATION.md` for architecture details
