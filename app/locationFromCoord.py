# Imports necessários
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import pandas as pd
import time

# Função para fazer geocodificação reversa com retry
def get_address_from_coordinates(lat, lon, max_retries=3):
    geolocator = Nominatim(user_agent="analysisFactory")
    
    for attempt in range(max_retries):
        try:
            location = geolocator.reverse((lat, lon), language="pt")
            if location:
                return {
                    'address': location.address,
                    'street': location.raw.get('address', {}).get('road'),
                    'house_number': location.raw.get('address', {}).get('house_number'),
                    'suburb': location.raw.get('address', {}).get('suburb'),
                    'city': location.raw.get('address', {}).get('city'),
                    'state': location.raw.get('address', {}).get('state'),
                    'postcode': location.raw.get('address', {}).get('postcode'),
                    'country': location.raw.get('address', {}).get('country'),
                    'raw_data': location.raw
                }
        except GeocoderTimedOut:
            if attempt == max_retries - 1:
                return None
            time.sleep(1)
    return None

# Função para processar múltiplas coordenadas
def process_coordinates_batch(df):
    results = []
    for idx, row in df.iterrows():
        print(f"Processando coordenada {idx + 1}/{len(df)}...")
        address = get_address_from_coordinates(row['latitude'], row['longitude'])
        if address:
            address['latitude'] = row['latitude']
            address['longitude'] = row['longitude']
            results.append(address)
        time.sleep(1)  # Respeitar limite de requisições
    return pd.DataFrame(results)

# Exemplo de uso com uma coordenada
lat, lon = -1.38085, -48.44300  # Coordenadas de São Paulo
result = get_address_from_coordinates(lat, lon)
print("Exemplo com uma coordenada:")
print(result)

# Exemplo com múltiplas coordenadas em um DataFrame
'''df = pd.DataFrame({
    'latitude': [-23.55052, -22.9068, -25.4284],
    'longitude': [-46.633308, -43.1729, -49.2733]
})

# Processar o DataFrame
result_df = process_coordinates_batch(df)
print("\nResultados completos:")
print(result_df)

# Salvar resultados em CSV (opcional)
result_df.to_csv('geocoding_results.csv', index=False)'''