import pandas as pd
from typing import List, Dict, Any
import logging
from datetime import datetime, date
import re

logger = logging.getLogger(__name__)

MONTHS = {
    1: "January",    2: "February", 3: "March",     4: "April",
    5: "May",        6: "June",     7: "July",      8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def csv_to_purchase_chunks(df: pd.DataFrame) -> List[Dict]:
    """
    Convert DataFrame rows to rich text chunks with comprehensive metadata.
    Enhanced to work with transform.py output (lowercase_underscore format).
    Returns list of dicts with 'text' and 'metadata' keys.
    """
    chunks: List[Dict] = []
    
    for _, row in df.iterrows():
        try:
            # Extract all field information using the lowercase_underscore format from transform.py
            metadata = {
                'transaction_id': getcol(row, "transaction_id"),
                'facility_id': getcol(row, "facility_id"),
                'facility_type': getcol(row, "facility_type"),
                'region': getcol(row, "region"),
                'bed_size': getcol(row, "bed_size"),
                'month': safe_int(row, "month"),
                'year': safe_int(row, "year"),
                'load_date': getcol(row, "load_date"),
                'vendor': getcol(row, "vendor"),
                'vendor_id': getcol(row, "vendor_id"),
                'manufacturer': getcol(row, "manufacturer"),
                'manufacturer_id': getcol(row, "manufacturer_id"),
                'catalog_num': getcol(row, "catalog_num"),
                'item_desc': getcol(row, "item_desc"),
                'department': getcol(row, "department"),
                'category': getcol(row, "category"),
                'quantity': safe_int(row, "quantity"),
                'price_paid': safe_float(row, "price_paid"),
                'total_spend': safe_float(row, "total_spend"),
                'unit_cost': safe_float(row, "unit_cost"),
            }
            
            # Create comprehensive, searchable text description
            text = _create_chunk_text(metadata)
            
            chunks.append({
                'text': text,
                'metadata': metadata
            })
            
        except Exception as e:
            logger.error(f"Failed to process row {_}: {e}")
            continue
            
    return chunks

def _create_chunk_text(metadata: Dict[str, Any]) -> str:
    """Create comprehensive text description from metadata"""
    parts = []
    
    # Temporal context
    month_val = metadata.get('month', 0)
    year_val = metadata.get('year', 0)
    if month_val > 0 and year_val > 0:
        month_name = MONTHS.get(month_val, f"Month-{month_val}")
        parts.append(f"In {month_name} {year_val}")
    
    # Facility information
    facility_type = metadata.get('facility_type', 'Unknown')
    facility_part = f"a {facility_type}"
    
    facility_id = metadata.get('facility_id')
    if facility_id and facility_id != 'Unknown':
        facility_part += f" (ID: {facility_id})"
    
    region = metadata.get('region')
    if region and region != 'Unknown':
        facility_part += f" in the {region} region"
    
    parts.append(facility_part)
    
    # Transaction details
    quantity = metadata.get('quantity', 0)
    item_desc = metadata.get('item_desc', 'Unknown item')
    
    if quantity > 0:
        purchase_part = f"Purchased {quantity} of {item_desc}"
        
        total_spend = metadata.get('total_spend', 0)
        if total_spend > 0:
            purchase_part += f" for ${total_spend:,.2f}"
            
        price_paid = metadata.get('price_paid', 0)
        if price_paid > 0:
            purchase_part += f" at ${price_paid:,.2f} each"
            
        parts.append(purchase_part)
    else:
        parts.append(f"Record for {item_desc}")
    
    # Vendor/manufacturer info
    vendor = metadata.get('vendor', 'Unknown vendor')
    manufacturer = metadata.get('manufacturer', 'Unknown manufacturer')
    
    if vendor != 'Unknown' or manufacturer != 'Unknown':
        vendor_part = f"From {vendor}"
        if manufacturer != vendor and manufacturer != 'Unknown':
            vendor_part += f" (manufactured by {manufacturer})"
        parts.append(vendor_part)
    
    # Department/category if available
    department = metadata.get('department')
    category = metadata.get('category')
    
    if department and department != 'Unknown':
        parts.append(f"Department: {department}")
    if category and category != 'Unknown':
        parts.append(f"Category: {category}")
    
    # Transaction ID if available
    transaction_id = metadata.get('transaction_id')
    if transaction_id and transaction_id != 'Unknown':
        parts.append(f"Transaction ID: {transaction_id}")
    
    return " | ".join(parts)

def getcol(row: pd.Series, name: str) -> str:
    """Get column value with fallback to different naming conventions"""
    # The transform.py outputs lowercase_underscore format, so prioritize that
    variants = [
        name.lower().replace(' ', '_'),  # Primary: lowercase_underscore
        name,                            # Exact match
        name.lower(),                    # Lowercase
        name.replace('_', '').lower(),   # No underscores lowercase
    ]
    
    for variant in variants:
        if variant in row.index:
            value = row[variant]
            # Return non-null, non-empty values
            if pd.notna(value) and str(value).strip() and str(value).strip().lower() not in ['unknown', 'null', 'none', '']:
                return str(value).strip()
    return "Unknown"

def safe_float(row: pd.Series, name: str) -> float:
    try:
        value = getcol(row, name)
        if value == "Unknown" or value == "":
            return 0.0
        return float(value.replace('$', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0.0

def safe_int(row: pd.Series, name: str) -> int:
    try:
        value = getcol(row, name)
        if value == "Unknown" or value == "":
            return 0
        return int(float(value))
    except (ValueError, TypeError):
        return 0

def validate_chunk_data(chunks: List[Dict]) -> Dict[str, Any]:
    """Validate the quality of generated chunks"""
    if not chunks:
        return {
            'valid': False,
            'message': "No chunks generated",
            'issues': ["Empty chunk list"]
        }
    
    issues = []
    valid_count = 0
    
    for chunk in chunks:
        # Check required fields
        missing_fields = []
        for field in ['transaction_id', 'facility_id', 'item_desc']:
            if not chunk['metadata'].get(field) or chunk['metadata'][field] == 'Unknown':
                missing_fields.append(field)
        
        if missing_fields:
            issues.append(f"Missing fields: {', '.join(missing_fields)}")
            continue
            
        # Check text quality
        text = chunk.get('text', '')
        if len(text) < 20:
            issues.append("Text too short")
            continue
            
        if len(text) > 2000:
            issues.append("Text too long")
            continue
            
        valid_count += 1
    
    validity_threshold = 0.8  # 80% of chunks must be valid
    validity_score = valid_count / len(chunks) if len(chunks) > 0 else 0
    
    return {
        'valid': validity_score >= validity_threshold,
        'message': f"{valid_count}/{len(chunks)} valid chunks ({validity_score:.1%})",
        'validity_score': validity_score,
        'issues': issues[:10]  # Return first 10 issues only
    }