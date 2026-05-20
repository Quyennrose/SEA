# Feature Engineering Formulas

All formulas should be computed on normalized 0-100 component scores unless otherwise noted. Missing components should not be filled with invented values; use source coverage flags and model-specific imputation policies.

## Tourism Demand Index

`TDI = 0.25 * search_volume_score + 0.25 * booking_velocity_score + 0.20 * hotel_occupancy_proxy + 0.15 * flight_search_score + 0.10 * event_impact_score + 0.05 * social_trend_score`

Use for demand forecasting, staffing, campaign timing, transport planning, and pricing inputs.

## Congestion Pressure Index

`CPI = 0.30 * crowd_density_score + 0.25 * traffic_delay_score + 0.15 * parking_pressure_score + 0.15 * transport_load_score + 0.10 * hotel_load_score + 0.05 * complaint_crowding_score`

Use for overload detection, real-time alerts, shuttle activation, and POI time-slot management.

## Tourism Economic Efficiency Index

`TEEI = 0.25 * revenue_per_capacity_score + 0.20 * local_business_participation_score + 0.20 * occupancy_balance_score + 0.15 * average_spending_score + 0.10 * stay_duration_score - 0.10 * infrastructure_stress_score`

Use for evaluating whether tourism volume creates sustainable local value.

## Tourist Redistribution Score

`TRS = 0.25 * target_free_capacity_score + 0.20 * travel_time_convenience_score + 0.20 * satisfaction_score + 0.15 * category_match_score + 0.10 * weather_suitability_score + 0.10 * economic_balance_score`

Use to rank alternative destinations, POIs, and time windows.

## Destination Capacity Score

`DCS = 0.30 * accommodation_capacity_score + 0.25 * transport_capacity_score + 0.20 * poi_capacity_score + 0.15 * infrastructure_capacity_score + 0.10 * environmental_resilience_score`

Use to identify safe receiving destinations during redistribution.

## Off-season Activation Score

`OSAS = 0.25 * unused_capacity_score + 0.20 * weather_suitability_score + 0.20 * event_readiness_score + 0.15 * price_discount_potential + 0.10 * social_interest_score + 0.10 * transport_accessibility_score`

Use to select off-season campaign targets and discount windows.

## Tourist Satisfaction Score

`TSS = 0.35 * review_score + 0.25 * sentiment_score + 0.15 * cleanliness_score + 0.10 * waiting_time_score + 0.10 * service_quality_score + 0.05 * return_intention_score`

Use to prevent redistribution into low-quality or high-complaint experiences.

## Infrastructure Stress Index

`ISI = 0.25 * traffic_stress_score + 0.20 * waste_pressure_score + 0.20 * water_usage_pressure_score + 0.15 * electricity_usage_pressure_score + 0.10 * emergency_service_load_score + 0.10 * environmental_pressure_score`

Use for local authority operations and sustainability safeguards.

