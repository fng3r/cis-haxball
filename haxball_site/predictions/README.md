# Predictions App

This Django app provides functionality for holding prediction tournaments based on matches played during the season.

## Features

- **Prediction Tournaments**: Manage which tournaments are available for predictions through Django admin
- **Tour-based Predictions**: Users make predictions for matches in specific tours
- **Time-based Access**: Predictions open 3 days before tour start and close at 18:00 on tour start date
- **Multiple Submissions**: Users can update their predictions multiple times until the tour closes
- **Result Tracking**: Automatic calculation of points based on match results
- **Standings Table**: Tournament standings with points for each tour and total points

## Models

### PredictionTournament
- Links to a League (tournament)
- Controls which tournaments are available for predictions
- Has `is_active` flag to enable/disable predictions

### PredictionSubmission
- Represents a user's submission for a specific tour
- One submission per user per tour per tournament
- Tracks creation and update timestamps

### Prediction
- Individual prediction for a match
- Stores predicted result (Home Win, Draw, Away Win)
- Automatically calculates points earned based on match results

## Views

### Main Page (`/predictions/`)
- Single page with three tabs:
  1. **Make Predictions**: View and edit current predictions
  2. **View Predictions**: Check other users' predictions (after tour closes)
  3. **Standings**: Tournament table with points

### Edit Predictions (`/predictions/edit/<tour_id>/`)
- Form to make predictions for all matches in a tour
- Real-time AJAX saving of individual predictions
- Shows match results and points earned for completed matches

## Admin Interface

- **PredictionTournament**: Manage which tournaments are available for predictions
- **PredictionSubmission**: View all user submissions with inline predictions
- **Prediction**: Individual prediction management

## Setup

1. **Add to INSTALLED_APPS**: The app is already added to settings
2. **Run migrations**: `python manage.py migrate`
3. **Set up prediction tournaments**: 
   ```bash
   python manage.py setup_predictions
   ```
4. **Configure tournaments**: Go to Django admin and enable/disable tournaments for predictions

## Usage

### For Users
1. Navigate to `/predictions/`
2. Select a tournament from the dropdown
3. Click "Make" or "Edit" for available tours
4. Make predictions for each match (P1, X, P2)
5. View standings and other users' predictions after tours close

### For Administrators
1. Go to Django admin
2. Under "Predictions" section:
   - Enable/disable tournaments for predictions
   - View all user submissions and predictions
   - Monitor prediction accuracy and points

## Points System

Currently implemented as a simple system:
- **Correct prediction**: 1 point
- **Incorrect prediction**: 0 points

The points calculation logic can be easily modified in the `Prediction.calculate_points()` method.

## Templates

All templates use the existing site's design system with Tailwind CSS classes and follow the established patterns.

## Customization

- **Points calculation**: Modify `Prediction.calculate_points()` method
- **Tour timing**: Adjust logic in `utils.py` functions
- **UI/UX**: Templates are in `templates/predictions/`
- **Admin interface**: Customize in `admin.py` 